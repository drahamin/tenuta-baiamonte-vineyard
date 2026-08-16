import express from 'express';
import QRCode from 'qrcode';
import pino from 'pino';
import fs from 'node:fs/promises';
import path from 'node:path';
import * as BaileysModule from '@whiskeysockets/baileys';

// Baileys 6 is published through more than one ESM/CommonJS export shape.
// Alpine/Node can expose the socket factory beneath one or two `default`
// wrappers even though desktop Node exposes it directly. Resolve both forms
// instead of assuming that the package default itself is callable.
function baileysExport(name) {
  return BaileysModule[name]
    ?? BaileysModule.default?.[name]
    ?? BaileysModule.default?.default?.[name];
}

const makeWASocket = [
  baileysExport('makeWASocket'),
  BaileysModule.default,
  BaileysModule.default?.default,
].find(value => typeof value === 'function');
const DisconnectReason = baileysExport('DisconnectReason');
const downloadMediaMessage = baileysExport('downloadMediaMessage');
const fetchLatestWaWebVersion = baileysExport('fetchLatestWaWebVersion');
const getContentType = baileysExport('getContentType');
const useMultiFileAuthState = baileysExport('useMultiFileAuthState');

if (![makeWASocket, downloadMediaMessage, fetchLatestWaWebVersion, getContentType, useMultiFileAuthState].every(value => typeof value === 'function')) {
  throw new Error('The installed Baileys package does not expose the required WhatsApp socket API');
}

const PORT = 8110;
const DATA_ROOT = '/data/system-whatsapp';
const CALLBACK_URL = 'http://127.0.0.1:8099/internal/system-whatsapp/inbound';
const TOKEN = process.env.SYSTEM_WHATSAPP_BRIDGE_TOKEN || '';
const logger = pino({ level: process.env.LOG_LEVEL === 'DEBUG' ? 'debug' : 'warn' });
const accounts = new Map();
let waWebVersionCache = null;
let waWebVersionFetchedAt = 0;

async function currentWaWebVersion() {
  const now = Date.now();
  if (waWebVersionCache && now - waWebVersionFetchedAt < 6 * 60 * 60 * 1000) return waWebVersionCache;
  const result = await fetchLatestWaWebVersion({ timeout: 15000 });
  if (!Array.isArray(result?.version) || result.version.length !== 3) {
    throw new Error('WhatsApp did not return a usable current Web client version');
  }
  waWebVersionCache = result.version;
  waWebVersionFetchedAt = now;
  return waWebVersionCache;
}

function accountState(slot) {
  if (!accounts.has(slot)) {
    accounts.set(slot, {
      slot,
      state: 'not_linked',
      socket: null,
      qr: null,
      qrDataUrl: null,
      identity: null,
      error: null,
      reconnectTimer: null,
      reconnectAttempts: 0,
      webVersion: null,
      chats: new Map(),
      contacts: new Map(),
      contactNumbers: new Map(),
      messages: new Map(),
      membershipRequests: new Map(),
      catalogRefreshedAt: null,
      catalogError: null,
      cacheLoaded: false,
      persistTimer: null,
      lastEventAt: null,
      receivedCount: 0,
      historyMessageCount: 0,
      historySyncAt: null,
      historySyncStatus: 'waiting',
    });
  }
  return accounts.get(slot);
}

function bareJid(jid = '') {
  return String(jid || '').replace(/@.+$/, '');
}

function usefulContactName(name, jid = '') {
  const value = String(name || '').trim();
  return Boolean(value && value !== bareJid(jid) && !/^\d{10,}$/.test(value));
}

function rememberContact(state, jid, candidates = [], phoneJid = '') {
  if (!jid) return;
  const existing = state.contacts.get(jid);
  const name = candidates.find(value => usefulContactName(value, jid));
  if (name) state.contacts.set(jid, String(name).trim().slice(0, 120));
  else if (!state.contacts.has(jid)) state.contacts.set(jid, bareJid(jid));
  if (phoneJid && /@s\.whatsapp\.net$/.test(phoneJid)) {
    state.contactNumbers.set(jid, bareJid(phoneJid));
    const currentName = state.contacts.get(jid) || existing;
    if (usefulContactName(currentName, jid)) rememberContact(state, phoneJid, [currentName]);
  }
}

async function resolveContactNumber(state, jid, supplied = '') {
  if (!jid) return '';
  const direct = [supplied, state.contactNumbers.get(jid)].find(value => /^(?:\d+)(?:@s\.whatsapp\.net)?$/.test(String(value || '')));
  if (direct) {
    const number = bareJid(direct);
    state.contactNumbers.set(jid, number);
    return number;
  }
  if (jid.endsWith('@s.whatsapp.net')) {
    const number = bareJid(jid);
    state.contactNumbers.set(jid, number);
    try {
      const lid = await state.socket?.signalRepository?.lidMapping?.getLIDForPN?.(jid);
      if (lid) {
        state.contactNumbers.set(lid, number);
        rememberContact(state, lid, [state.contacts.get(jid)], jid);
        rememberContact(state, jid, [state.contacts.get(lid)]);
      }
    } catch (_) {}
    return number;
  }
  if (!jid.endsWith('@lid')) return '';
  try {
    const mapped = await state.socket?.signalRepository?.lidMapping?.getPNForLID?.(jid);
    if (mapped) {
      const number = bareJid(mapped);
      state.contactNumbers.set(jid, number);
      rememberContact(state, mapped, [state.contacts.get(jid)]);
      rememberContact(state, jid, [state.contacts.get(mapped)], mapped);
      return number;
    }
  } catch (_) {}
  return '';
}

function contactDisplayName(state, jid) {
  const name = state.contacts.get(jid);
  if (usefulContactName(name, jid)) return name;
  const number = state.contactNumbers.get(jid);
  return number ? `WhatsApp ${number}` : `Unnamed WhatsApp contact · …${bareJid(jid).slice(-5)}`;
}

function safeAccount(state, includeQr = false) {
  const contacts = new Map(state.contacts);
  for (const chat of state.chats.values()) {
    if (chat.kind === 'direct' && !contacts.has(chat.chat_id)) contacts.set(chat.chat_id, chat.name || bareJid(chat.chat_id));
  }
  return {
    slot: state.slot,
    state: state.state,
    linked: Boolean(state.identity),
    identity: state.identity,
    error: state.error,
    web_version: state.webVersion ? state.webVersion.join('.') : null,
    last_event_at: state.lastEventAt,
    received_count: state.receivedCount,
    history_message_count: state.historyMessageCount,
    history_sync_at: state.historySyncAt,
    history_sync_status: state.historySyncStatus,
    catalog_refreshed_at: state.catalogRefreshedAt,
    catalog_error: state.catalogError,
    contacts: [...contacts.entries()]
      .filter(([contact_id]) => {
        if (!contact_id.endsWith('@s.whatsapp.net')) return true;
        const number = bareJid(contact_id);
        return ![...contacts.keys()].some(candidate => candidate.endsWith('@lid') && state.contactNumbers.get(candidate) === number);
      })
      .map(([contact_id]) => ({
        contact_id,
        name: contactDisplayName(state, contact_id),
        number: state.contactNumbers.get(contact_id) || (contact_id.endsWith('@s.whatsapp.net') ? bareJid(contact_id) : ''),
        unresolved: !usefulContactName(state.contacts.get(contact_id), contact_id),
      }))
      .sort((a, b) => String(a.name).localeCompare(String(b.name)))
      .slice(0, 500),
    membership_requests: [...state.membershipRequests.values()]
      .sort((a, b) => String(b.received_at || '').localeCompare(String(a.received_at || ''))),
    qr_data_url: includeQr ? state.qrDataUrl : null,
    chats: [...state.chats.values()]
      .map(chat => chat.kind === 'direct' ? { ...chat, name: contactDisplayName(state, chat.chat_id) } : chat)
      .sort((a, b) => String(b.last_message_at || '').localeCompare(String(a.last_message_at || '')))
      .slice(0, 250),
  };
}

async function importContactNames(state, rows = []) {
  if (state.state !== 'connected' || !state.socket) throw new Error('This system account is not connected');
  let imported = 0;
  let paired = 0;
  for (const row of rows.slice(0, 2000)) {
    const name = String(row?.name || '').trim().slice(0, 120);
    const number = String(row?.number || '').replace(/\D/g, '');
    if (!name || number.length < 7 || number.length > 15) continue;
    const pn = `${number}@s.whatsapp.net`;
    rememberContact(state, pn, [name]);
    state.contactNumbers.set(pn, number);
    let lid = '';
    try { lid = await state.socket?.signalRepository?.lidMapping?.getLIDForPN?.(pn) || ''; } catch (_) {}
    if (!lid) lid = [...state.contactNumbers.entries()].find(([candidate, value]) => candidate.endsWith('@lid') && value === number)?.[0] || '';
    if (lid) {
      rememberContact(state, lid, [name], pn);
      if (state.chats.has(lid)) await updateChat(state, lid, { name });
      paired += 1;
    }
    if (state.chats.has(pn)) await updateChat(state, pn, { name });
    imported += 1;
  }
  state.catalogRefreshedAt = new Date().toISOString();
  schedulePersist(state);
  return { imported, paired, account: safeAccount(state, false) };
}

function accountBackup(state) {
  return {
    format: 'baiamonte-system-whatsapp-backup-v1',
    exported_at: new Date().toISOString(),
    slot: state.slot,
    identity: state.identity,
    contacts: [...state.contacts.entries()],
    contact_numbers: [...state.contactNumbers.entries()],
    chats: [...state.chats.entries()],
    messages: [...state.messages.entries()],
  };
}

function rememberMessage(state, chatId, row) {
  const rows = state.messages.get(chatId) || [];
  if (row.message_id && rows.some(item => item.message_id === row.message_id)) return;
  rows.push(row);
  rows.sort((a, b) => String(a.occurred_at || '').localeCompare(String(b.occurred_at || '')));
  state.messages.set(chatId, rows.slice(-150));
  schedulePersist(state);
}

function cachePath(state) {
  return path.join(DATA_ROOT, `account-${state.slot}`, 'catalog.json');
}

async function persistAccountCache(state) {
  state.persistTimer = null;
  const payload = {
    identity: state.identity,
    catalog_refreshed_at: state.catalogRefreshedAt,
    contacts: [...state.contacts.entries()].slice(0, 1000),
    contact_numbers: [...state.contactNumbers.entries()].slice(0, 1000),
    chats: [...state.chats.entries()].slice(0, 500),
    messages: [...state.messages.entries()].slice(0, 250),
    history_message_count: state.historyMessageCount,
    history_sync_at: state.historySyncAt,
    history_sync_status: state.historySyncStatus,
  };
  await fs.writeFile(cachePath(state), JSON.stringify(payload), 'utf8');
}

function schedulePersist(state) {
  if (state.persistTimer) return;
  state.persistTimer = setTimeout(() => persistAccountCache(state).catch(error => {
    console.warn(`[system-whatsapp:${state.slot}] cache save failed: ${String(error?.message || error).slice(0, 240)}`);
  }), 1200);
}

async function loadAccountCache(state) {
  if (state.cacheLoaded) return;
  state.cacheLoaded = true;
  try {
    const payload = JSON.parse(await fs.readFile(cachePath(state), 'utf8'));
    state.identity = payload.identity || state.identity;
    state.catalogRefreshedAt = payload.catalog_refreshed_at || null;
    state.contacts = new Map(Array.isArray(payload.contacts) ? payload.contacts : []);
    state.contactNumbers = new Map(Array.isArray(payload.contact_numbers) ? payload.contact_numbers : []);
    state.chats = new Map(Array.isArray(payload.chats) ? payload.chats : []);
    state.messages = new Map(Array.isArray(payload.messages) ? payload.messages : []);
    state.historyMessageCount = Number(payload.history_message_count || 0);
    state.historySyncAt = payload.history_sync_at || null;
    state.historySyncStatus = payload.history_sync_status || 'waiting';
  } catch (error) {
    if (error?.code !== 'ENOENT') console.warn(`[system-whatsapp:${state.slot}] cache load failed: ${String(error?.message || error).slice(0, 240)}`);
  }
}

function inviteInfo(message = {}) {
  let value = message;
  for (const wrapper of ['ephemeralMessage', 'viewOnceMessage', 'viewOnceMessageV2']) {
    if (value?.[wrapper]?.message) value = value[wrapper].message;
  }
  const invite = value?.groupInviteMessage;
  if (!invite?.inviteCode) return null;
  return {
    group_id: invite.groupJid || '',
    group_name: invite.groupName || 'WhatsApp group',
    invite_code: invite.inviteCode,
    expires_at: invite.inviteExpiration ? new Date(Number(invite.inviteExpiration) * 1000).toISOString() : null,
  };
}

function cleanText(message = {}) {
  let value = message;
  for (const wrapper of ['ephemeralMessage', 'viewOnceMessage', 'viewOnceMessageV2', 'documentWithCaptionMessage']) {
    if (value?.[wrapper]?.message) value = value[wrapper].message;
  }
  return value.conversation
    || value.extendedTextMessage?.text
    || value.imageMessage?.caption
    || value.videoMessage?.caption
    || value.documentMessage?.caption
    || '';
}

function mediaInfo(message = {}) {
  const type = getContentType(message);
  const supported = new Set(['imageMessage', 'videoMessage', 'audioMessage', 'documentMessage', 'stickerMessage']);
  if (!supported.has(type)) return null;
  const value = message[type] || {};
  return {
    type: type.replace('Message', ''),
    filename: value.fileName || `${type.replace('Message', '')}-${Date.now()}`,
    content_type: value.mimetype || 'application/octet-stream',
  };
}

async function callback(payload) {
  const response = await fetch(CALLBACK_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-System-WhatsApp-Token': TOKEN,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Vineyard intake returned ${response.status}`);
}

async function updateChat(state, jid, patch = {}) {
  if (!jid || jid === 'status@broadcast') return;
  const previous = state.chats.get(jid) || { chat_id: jid };
  const isGroup = jid.endsWith('@g.us');
  const candidateName = [patch.name, previous.name, state.contacts.get(jid)].find(value => usefulContactName(value, jid));
  let name = candidateName || contactDisplayName(state, jid);
  if (isGroup && state.socket && (!previous.name || previous.name === jid.replace(/@.+$/, ''))) {
    try {
      const metadata = await state.socket.groupMetadata(jid);
      name = metadata.subject || name;
    } catch (_) {}
  }
  state.chats.set(jid, {
    ...previous,
    ...patch,
    chat_id: jid,
    name,
    kind: isGroup ? 'group' : 'direct',
  });
  schedulePersist(state);
}

async function refreshAccountCatalog(state) {
  if (state.state !== 'connected' || !state.socket) throw new Error('This system account is not connected');
  state.catalogError = null;
  try {
    const participating = await state.socket.groupFetchAllParticipating();
    for (const [groupId, metadata] of Object.entries(participating || {})) {
      await updateChat(state, groupId, {
        name: metadata?.subject || groupId.replace(/@.+$/, ''),
        participant_count: Array.isArray(metadata?.participants) ? metadata.participants.length : null,
      });
      for (const participant of metadata?.participants || []) {
        const jid = participant?.id || participant?.jid;
        const phoneJid = participant?.phoneNumber || participant?.phone_number || participant?.pn || '';
        if (jid) {
          rememberContact(state, jid, [participant?.notify, participant?.name, participant?.verifiedName, participant?.username], phoneJid);
          await resolveContactNumber(state, jid, phoneJid);
        }
      }
    }
    for (const jid of state.contacts.keys()) await resolveContactNumber(state, jid);
    state.catalogRefreshedAt = new Date().toISOString();
    state.lastEventAt = state.catalogRefreshedAt;
    schedulePersist(state);
  } catch (error) {
    state.catalogError = String(error?.message || error).slice(0, 300);
    state.lastEventAt = new Date().toISOString();
    throw error;
  }
  return safeAccount(state, false);
}

async function syncPriorChats(state) {
  if (state.state !== 'connected' || !state.socket) throw new Error('This system account is not connected');
  await refreshAccountCatalog(state);
  let requested = 0;
  for (const [chatId, rows] of state.messages.entries()) {
    const oldest = (rows || []).find(row => row.message_key && row.message_timestamp);
    if (!oldest) continue;
    try {
      await state.socket.fetchMessageHistory(50, oldest.message_key, oldest.message_timestamp);
      requested += 1;
    } catch (_) {}
    if (requested >= 25) break;
  }
  state.historySyncAt = new Date().toISOString();
  state.historySyncStatus = requested ? `requested for ${requested} chats` : 'relink_required';
  state.lastEventAt = state.historySyncAt;
  schedulePersist(state);
  return {
    ...safeAccount(state, false),
    history_request_count: requested,
    relink_required: requested === 0 && state.historyMessageCount === 0,
    message: requested
      ? `Requested up to 50 older messages for ${requested} chat(s). Keep the phone online while WhatsApp responds.`
      : state.historyMessageCount
        ? 'Previously synchronized history is already retained.'
        : 'WhatsApp did not provide a prior-history seed for this linked device. To import older chats, unlink and link this account once more, then keep the phone online until the initial sync completes.',
  };
}

async function processMessage(state, item, ingest = true) {
  const key = item?.key || {};
  if (!item?.message || !key.remoteJid || key.remoteJid === 'status@broadcast') return;
  const chatId = key.remoteJid;
  const isGroup = chatId.endsWith('@g.us');
  const senderJid = isGroup ? (key.participant || item.participant || '') : chatId;
  const senderAlt = isGroup ? (key.participantAlt || key.participantPn || '') : (key.remoteJidAlt || key.senderPn || '');
  rememberContact(state, senderJid, [item.pushName], senderAlt);
  await resolveContactNumber(state, senderJid, senderAlt);
  if (senderAlt) rememberContact(state, senderAlt, [item.pushName, state.contacts.get(senderJid)]);
  const text = cleanText(item.message).trim();
  const media = mediaInfo(item.message);
  const timestamp = Number(item.messageTimestamp || 0);
  const receivedAt = timestamp ? new Date(timestamp * 1000).toISOString() : new Date().toISOString();
  await updateChat(state, chatId, { last_message: text.slice(0, 180), last_message_at: receivedAt });
  const invite = inviteInfo(item.message);
  if (invite && !key.fromMe) {
    const requestId = `invite:${key.id || invite.invite_code}`;
    state.membershipRequests.set(requestId, {
      request_id: requestId,
      kind: 'group_invite',
      ...invite,
      sender_id: senderJid,
      sender_name: item.pushName || contactDisplayName(state, senderJid),
      received_at: receivedAt,
    });
    state.lastEventAt = new Date().toISOString();
    return;
  }
  rememberMessage(state, chatId, {
    message_id: String(key.id || `${Date.now()}`),
    from_me: Boolean(key.fromMe),
    sender_id: senderJid,
    sender_name: key.fromMe ? (state.identity?.name || 'Baiamonte') : (item.pushName || contactDisplayName(state, senderJid)),
    text: text || (media ? `[${media.type}]` : '[message]'),
    message_type: media?.type || 'text',
    occurred_at: receivedAt,
    message_key: key,
    message_timestamp: timestamp || null,
  });
  if (key.fromMe || !ingest) return;
  const payload = {
    account_slot: state.slot,
    message_id: String(key.id || `${Date.now()}`),
    chat_id: chatId,
    chat_name: state.chats.get(chatId)?.name || chatId,
    is_group: isGroup,
    sender_id: senderJid,
    sender_name: item.pushName || contactDisplayName(state, senderJid),
    received_at: receivedAt,
    text,
    message_type: media?.type || 'text',
  };
  if (media) {
    try {
      const buffer = await downloadMediaMessage(item, 'buffer', {}, {
        logger,
        reuploadRequest: state.socket?.updateMediaMessage,
      });
      if (buffer?.length && buffer.length <= 20 * 1024 * 1024) {
        payload.attachment = {
          filename: media.filename,
          content_type: media.content_type,
          data_base64: buffer.toString('base64'),
        };
      } else if (buffer?.length) {
        payload.attachment_error = 'Attachment is larger than 20 MB';
      }
    } catch (error) {
      payload.attachment_error = String(error?.message || error).slice(0, 300);
    }
  }
  if (!payload.text && !payload.attachment && !payload.attachment_error) return;
  await callback(payload);
  state.receivedCount += 1;
  state.lastEventAt = new Date().toISOString();
}

async function startAccount(slot, force = false) {
  const state = accountState(slot);
  if (state.socket && !force) return safeAccount(state, true);
  if (state.reconnectTimer) clearTimeout(state.reconnectTimer);
  state.reconnectTimer = null;
  if (force && state.socket) {
    try { state.socket.end(); } catch (_) {}
    state.socket = null;
  }
  state.state = 'connecting';
  state.error = null;
  state.qr = null;
  state.qrDataUrl = null;
  const authDir = path.join(DATA_ROOT, `account-${slot}`);
  await fs.mkdir(authDir, { recursive: true });
  await loadAccountCache(state);
  const { state: authState, saveCreds } = await useMultiFileAuthState(authDir);
  const version = await currentWaWebVersion();
  state.webVersion = version;
  const socket = makeWASocket({
    version,
    auth: authState,
    logger,
    printQRInTerminal: false,
    browser: ['Tenuta Baiamonte', 'Vineyard Operations', '1.0'],
    syncFullHistory: true,
    shouldSyncHistoryMessage: () => true,
    markOnlineOnConnect: false,
    generateHighQualityLinkPreview: false,
  });
  state.socket = socket;
  socket.ev.on('creds.update', saveCreds);
  socket.ev.on('contacts.upsert', async rows => {
    for (const row of rows || []) {
      if (!row.id) continue;
      const phoneJid = row.phoneNumber || row.phone_number || row.pn || '';
      rememberContact(state, row.id, [row.notify, row.name, row.verifiedName, row.pushName], phoneJid);
      await resolveContactNumber(state, row.id, phoneJid);
    }
    schedulePersist(state);
  });
  socket.ev.on('contacts.update', async rows => {
    for (const row of rows || []) {
      if (!row.id) continue;
      const phoneJid = row.phoneNumber || row.phone_number || row.pn || '';
      rememberContact(state, row.id, [row.notify, row.name, row.verifiedName, row.pushName], phoneJid);
      await resolveContactNumber(state, row.id, phoneJid);
    }
    schedulePersist(state);
  });
  socket.ev.on('lid-mapping.update', update => {
    for (const [left, rightValue] of Object.entries(update || {})) {
      const right = typeof rightValue === 'string' ? rightValue : (rightValue?.pn || rightValue?.jid || rightValue?.phoneNumber || '');
      const lid = left.endsWith('@lid') ? left : (right.endsWith('@lid') ? right : '');
      const pn = left.endsWith('@s.whatsapp.net') ? left : (right.endsWith('@s.whatsapp.net') ? right : '');
      if (lid && pn) {
        state.contactNumbers.set(lid, bareJid(pn));
        rememberContact(state, lid, [state.contacts.get(pn)]);
      }
    }
    schedulePersist(state);
  });
  socket.ev.on('chats.upsert', rows => rows.forEach(row => updateChat(state, row.id, {
    name: row.name,
    last_message_at: row.conversationTimestamp ? new Date(Number(row.conversationTimestamp) * 1000).toISOString() : null,
  })));
  socket.ev.on('chats.update', rows => rows.forEach(row => updateChat(state, row.id, {
    name: row.name,
    last_message_at: row.conversationTimestamp ? new Date(Number(row.conversationTimestamp) * 1000).toISOString() : undefined,
  })));
  socket.ev.on('groups.upsert', rows => rows.forEach(row => updateChat(state, row.id, {
    name: row.subject,
    participant_count: Array.isArray(row.participants) ? row.participants.length : null,
  })));
  socket.ev.on('groups.update', rows => rows.forEach(row => updateChat(state, row.id, { name: row.subject })));
  socket.ev.on('messaging-history.set', async history => {
    for (const row of history.contacts || []) {
      if (!row.id) continue;
      const phoneJid = row.phoneNumber || row.phone_number || row.pn || '';
      rememberContact(state, row.id, [row.notify, row.name, row.verifiedName, row.pushName], phoneJid);
      await resolveContactNumber(state, row.id, phoneJid);
    }
    (history.chats || []).forEach(row => updateChat(state, row.id, { name: row.name }));
    (history.messages || []).forEach(item => {
      const key = item?.key || {};
      if (!item?.message || !key.remoteJid || key.remoteJid === 'status@broadcast') return;
      const chatId = key.remoteJid;
      const senderJid = chatId.endsWith('@g.us') ? (key.participant || item.participant || '') : chatId;
      const senderAlt = chatId.endsWith('@g.us') ? (key.participantAlt || key.participantPn || '') : (key.remoteJidAlt || key.senderPn || '');
      rememberContact(state, senderJid, [item.pushName], senderAlt);
      resolveContactNumber(state, senderJid, senderAlt);
      if (senderAlt) rememberContact(state, senderAlt, [item.pushName, state.contacts.get(senderJid)]);
      const timestamp = Number(item.messageTimestamp || 0);
      const occurredAt = timestamp ? new Date(timestamp * 1000).toISOString() : new Date().toISOString();
      const text = cleanText(item.message).trim();
      const media = mediaInfo(item.message);
      updateChat(state, chatId, { last_message: text.slice(0, 180), last_message_at: occurredAt });
      rememberMessage(state, chatId, {
        message_id: String(key.id || `${timestamp}-${senderJid}`),
        from_me: Boolean(key.fromMe),
        sender_id: senderJid,
        sender_name: key.fromMe ? (state.identity?.name || 'Baiamonte') : (item.pushName || contactDisplayName(state, senderJid)),
        text: text || (media ? `[${media.type}]` : '[message]'),
        message_type: media?.type || 'text',
        occurred_at: occurredAt,
        message_key: key,
        message_timestamp: timestamp || null,
      });
    });
    state.historyMessageCount += (history.messages || []).length;
    state.historySyncAt = new Date().toISOString();
    state.historySyncStatus = history.isLatest === false ? `syncing ${Number(history.progress || 0)}%` : 'complete';
    state.catalogRefreshedAt = new Date().toISOString();
    schedulePersist(state);
  });
  socket.ev.on('messages.upsert', async event => {
    if (!['notify', 'append'].includes(event.type)) return;
    for (const item of event.messages || []) {
      try { await processMessage(state, item, event.type === 'notify'); }
      catch (error) {
        state.error = String(error?.message || error).slice(0, 300);
        state.lastEventAt = new Date().toISOString();
      }
    }
    if (event.type === 'append' && (event.messages || []).length) {
      state.historyMessageCount += event.messages.length;
      state.historySyncAt = new Date().toISOString();
      state.historySyncStatus = 'complete';
      schedulePersist(state);
    }
  });
  socket.ev.on('connection.update', async update => {
    if (update.qr) {
      state.state = 'scan_qr';
      state.reconnectAttempts = 0;
      state.qr = update.qr;
      state.qrDataUrl = await QRCode.toDataURL(update.qr, { width: 360, margin: 2, color: { dark: '#10100f', light: '#fffdf4' } });
    }
    if (update.connection === 'open') {
      state.state = 'connected';
      state.reconnectAttempts = 0;
      state.qr = null;
      state.qrDataUrl = null;
      state.identity = {
        id: socket.user?.id || null,
        name: socket.user?.name || null,
      };
      state.error = null;
      state.lastEventAt = new Date().toISOString();
      schedulePersist(state);
      refreshAccountCatalog(state).catch(error => {
        console.warn(`[system-whatsapp:${slot}] catalogue refresh failed: ${String(error?.message || error).slice(0, 300)}`);
      });
    }
    if (update.connection === 'close') {
      state.socket = null;
      const disconnectError = update.lastDisconnect?.error;
      const code = disconnectError?.output?.statusCode;
      const reason = disconnectError?.data?.reason;
      const location = disconnectError?.data?.location;
      const loggedOut = code === DisconnectReason.loggedOut;
      state.state = loggedOut ? 'not_linked' : 'disconnected';
      state.error = loggedOut
        ? 'Account was logged out from WhatsApp.'
        : [String(disconnectError?.message || 'Connection closed'), code ? `HTTP ${code}` : null, reason ? `reason ${reason}` : null, location ? `region ${location}` : null]
            .filter(Boolean).join(' · ').slice(0, 300);
      state.lastEventAt = new Date().toISOString();
      console.warn(`[system-whatsapp:${slot}] disconnected: ${state.error}`);
      if (!loggedOut && state.reconnectAttempts < 5) {
        state.reconnectAttempts += 1;
        const delayMs = Math.min(5000 * (2 ** (state.reconnectAttempts - 1)), 60000);
        state.reconnectTimer = setTimeout(() => startAccount(slot).catch(error => {
          state.error = String(error?.message || error).slice(0, 300);
          console.warn(`[system-whatsapp:${slot}] reconnect failed: ${state.error}`);
        }), delayMs);
      }
    }
  });
  return safeAccount(state, true);
}

async function forgetAccount(slot) {
  const state = accountState(slot);
  if (state.reconnectTimer) clearTimeout(state.reconnectTimer);
  try { await state.socket?.logout(); } catch (_) {}
  try { state.socket?.end(); } catch (_) {}
  await fs.rm(path.join(DATA_ROOT, `account-${slot}`), { recursive: true, force: true });
  accounts.delete(slot);
  return safeAccount(accountState(slot), false);
}

async function relinkAccount(slot) {
  const state = accountState(slot);
  if (state.reconnectTimer) clearTimeout(state.reconnectTimer);
  try { state.socket?.end(); } catch (_) {}
  const directory = path.join(DATA_ROOT, `account-${slot}`);
  for (const entry of await fs.readdir(directory, { withFileTypes: true }).catch(() => [])) {
    if (entry.name === 'catalog.json') continue;
    await fs.rm(path.join(directory, entry.name), { recursive: true, force: true });
  }
  state.socket = null;
  state.identity = null;
  state.state = 'not_linked';
  state.qr = null;
  state.qrDataUrl = null;
  state.error = null;
  state.cacheLoaded = true;
  return startAccount(slot, true);
}

const app = express();
app.use(express.json({ limit: '3mb' }));
app.use((req, res, next) => {
  if (!TOKEN || req.get('Authorization') !== `Bearer ${TOKEN}`) return res.status(403).json({ error: 'Forbidden' });
  next();
});
app.get('/health', (_req, res) => res.json({ available: true, accounts: [1, 2].map(slot => safeAccount(accountState(slot), false)) }));
app.get('/accounts', (_req, res) => res.json({ accounts: [1, 2].map(slot => safeAccount(accountState(slot), true)) }));
app.post('/accounts/:slot/connect', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  try { res.json(await startAccount(slot, Boolean(req.body?.restart))); }
  catch (error) { res.status(502).json({ error: String(error?.message || error).slice(0, 300) }); }
});
app.post('/accounts/:slot/disconnect', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  try { res.json(await forgetAccount(slot)); }
  catch (error) { res.status(502).json({ error: String(error?.message || error).slice(0, 300) }); }
});
app.post('/accounts/:slot/relink', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  try { res.json(await relinkAccount(slot)); }
  catch (error) { res.status(502).json({ error: String(error?.message || error).slice(0, 300) }); }
});
app.get('/accounts/:slot/backup', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  await loadAccountCache(state);
  res.json(accountBackup(state));
});
app.post('/accounts/:slot/send', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  const chatId = String(req.body?.chat_id || '').trim();
  const text = String(req.body?.text || '').trim();
  if (state.state !== 'connected' || !state.socket) return res.status(409).json({ error: 'This system account is not connected' });
  if (!state.chats.has(chatId)) return res.status(422).json({ error: 'Choose a chat already visible on this linked account' });
  if (!text || text.length > 4096) return res.status(422).json({ error: 'Enter a message of 1 to 4096 characters' });
  try {
    const sent = await state.socket.sendMessage(chatId, { text });
    const sentAt = new Date().toISOString();
    await updateChat(state, chatId, { last_message: text.slice(0, 180), last_message_at: sentAt });
    rememberMessage(state, chatId, {
      message_id: sent?.key?.id || `${Date.now()}`,
      from_me: true,
      sender_id: state.identity?.id || '',
      sender_name: state.identity?.name || 'Baiamonte',
      text,
      message_type: 'text',
      occurred_at: sentAt,
    });
    state.lastEventAt = sentAt;
    res.json({ sent: true, account_slot: slot, chat_id: chatId, message_id: sent?.key?.id || null, sent_at: sentAt });
  } catch (error) {
    res.status(502).json({ error: String(error?.message || error).slice(0, 300) });
  }
});
app.post('/accounts/:slot/contacts', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  const number = String(req.body?.number || '').replace(/\D/g, '');
  const name = String(req.body?.name || '').trim().slice(0, 120);
  if (state.state !== 'connected' || !state.socket) return res.status(409).json({ error: 'This system account is not connected' });
  if (number.length < 7 || number.length > 15) return res.status(422).json({ error: 'Enter a complete international number' });
  try {
    const matches = await state.socket.onWhatsApp(number);
    const jid = matches?.find(item => item.exists)?.jid;
    if (!jid) return res.status(404).json({ error: 'That number is not available on WhatsApp' });
    state.contacts.set(jid, name || number);
    await updateChat(state, jid, { name: name || number });
    res.json({ added: true, contact: { contact_id: jid, number, name: name || number } });
  } catch (error) {
    res.status(502).json({ error: String(error?.message || error).slice(0, 300) });
  }
});
app.post('/accounts/:slot/contacts/import', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  if (!Array.isArray(req.body?.contacts)) return res.status(422).json({ error: 'Provide a contacts list' });
  try { res.json(await importContactNames(accountState(slot), req.body.contacts)); }
  catch (error) { res.status(502).json({ error: String(error?.message || error).slice(0, 300) }); }
});
app.put('/accounts/:slot/contacts/:contactId', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  const contactId = decodeURIComponent(req.params.contactId);
  const name = String(req.body?.name || '').trim().slice(0, 120);
  if (!state.contacts.has(contactId)) return res.status(404).json({ error: 'That contact is not visible on this linked account' });
  if (!name) return res.status(422).json({ error: 'Enter a contact name' });
  rememberContact(state, contactId, [name]);
  const number = state.contactNumbers.get(contactId) || (contactId.endsWith('@s.whatsapp.net') ? bareJid(contactId) : '');
  if (number) {
    const pn = `${number}@s.whatsapp.net`;
    rememberContact(state, pn, [name]);
    for (const [candidate, candidateNumber] of state.contactNumbers.entries()) {
      if (candidateNumber === number) rememberContact(state, candidate, [name], pn);
    }
  }
  if (state.chats.has(contactId)) await updateChat(state, contactId, { name });
  schedulePersist(state);
  res.json({ updated: true, contact: { contact_id: contactId, name, number: state.contactNumbers.get(contactId) || '' } });
});
app.post('/accounts/:slot/catalog/refresh', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  try { res.json(await refreshAccountCatalog(state)); }
  catch (error) { res.status(502).json({ error: String(error?.message || error).slice(0, 300) }); }
});
app.post('/accounts/:slot/history/sync', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  try { res.json(await syncPriorChats(accountState(slot))); }
  catch (error) { res.status(502).json({ error: String(error?.message || error).slice(0, 300) }); }
});
app.get('/accounts/:slot/chats/:chatId/messages', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  const chatId = decodeURIComponent(req.params.chatId);
  if (!state.chats.has(chatId) && state.contacts.has(chatId)) await updateChat(state, chatId, { name: state.contacts.get(chatId) });
  if (!state.chats.has(chatId)) return res.status(404).json({ error: 'Chat is not visible on this account' });
  const chat = { ...state.chats.get(chatId) };
  if (chat.kind === 'direct') chat.name = contactDisplayName(state, chatId);
  const messages = (state.messages.get(chatId) || []).slice(-100).map(row => ({
    ...row,
    sender_name: row.from_me ? (state.identity?.name || 'Baiamonte') : contactDisplayName(state, row.sender_id || chatId),
  }));
  res.json({ chat, messages });
});
app.post('/accounts/:slot/membership/refresh', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  if (state.state !== 'connected' || !state.socket) return res.status(409).json({ error: 'This system account is not connected' });
  for (const chat of [...state.chats.values()].filter(item => item.kind === 'group').slice(0, 80)) {
    try {
      const requests = await state.socket.groupRequestParticipantsList(chat.chat_id);
      for (const participant of requests || []) {
        const jid = participant.jid || participant.id || participant.participant;
        if (!jid) continue;
        const requestId = `join:${chat.chat_id}:${jid}`;
        state.membershipRequests.set(requestId, {
          request_id: requestId,
          kind: 'join_request',
          group_id: chat.chat_id,
          group_name: chat.name,
          participant_id: jid,
          participant_name: state.contacts.get(jid) || jid.replace(/@.+$/, ''),
          received_at: new Date().toISOString(),
        });
      }
    } catch (_) {}
  }
  res.json(safeAccount(state, false));
});
app.post('/accounts/:slot/membership/:requestId', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  const requestId = decodeURIComponent(req.params.requestId);
  const request = state.membershipRequests.get(requestId);
  const decision = String(req.body?.decision || '');
  if (!request) return res.status(404).json({ error: 'Membership request is no longer pending' });
  if (!['approve', 'reject'].includes(decision)) return res.status(422).json({ error: 'Choose approve or reject' });
  if (state.state !== 'connected' || !state.socket) return res.status(409).json({ error: 'This system account is not connected' });
  try {
    if (request.kind === 'group_invite' && decision === 'approve') await state.socket.groupAcceptInvite(request.invite_code);
    if (request.kind === 'join_request') await state.socket.groupRequestParticipantsUpdate(request.group_id, [request.participant_id], decision);
    state.membershipRequests.delete(requestId);
    res.json({ completed: true, decision, request_id: requestId });
  } catch (error) {
    res.status(502).json({ error: String(error?.message || error).slice(0, 300) });
  }
});

await fs.mkdir(DATA_ROOT, { recursive: true });
for (const slot of [1, 2]) {
  try {
    await fs.access(path.join(DATA_ROOT, `account-${slot}`, 'creds.json'));
    startAccount(slot).catch(error => { accountState(slot).error = String(error?.message || error).slice(0, 300); });
  } catch (_) {}
}
app.listen(PORT, '127.0.0.1', () => logger.info(`System WhatsApp bridge listening on ${PORT}`));
