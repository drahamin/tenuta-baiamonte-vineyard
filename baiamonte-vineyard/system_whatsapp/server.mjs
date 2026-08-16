import express from 'express';
import QRCode from 'qrcode';
import pino from 'pino';
import fs from 'node:fs/promises';
import path from 'node:path';
import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  getContentType,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';

const PORT = 8110;
const DATA_ROOT = '/data/system-whatsapp';
const CALLBACK_URL = 'http://127.0.0.1:8099/internal/system-whatsapp/inbound';
const TOKEN = process.env.SYSTEM_WHATSAPP_BRIDGE_TOKEN || '';
const logger = pino({ level: process.env.LOG_LEVEL === 'DEBUG' ? 'debug' : 'warn' });
const accounts = new Map();

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
      chats: new Map(),
      contacts: new Map(),
      messages: new Map(),
      membershipRequests: new Map(),
      lastEventAt: null,
      receivedCount: 0,
    });
  }
  return accounts.get(slot);
}

function safeAccount(state, includeQr = false) {
  const contacts = new Map(state.contacts);
  for (const chat of state.chats.values()) {
    if (chat.kind === 'direct' && !contacts.has(chat.chat_id)) contacts.set(chat.chat_id, chat.name || chat.chat_id.replace(/@.+$/, ''));
  }
  return {
    slot: state.slot,
    state: state.state,
    linked: Boolean(state.identity),
    identity: state.identity,
    error: state.error,
    last_event_at: state.lastEventAt,
    received_count: state.receivedCount,
    contacts: [...contacts.entries()]
      .map(([contact_id, name]) => ({ contact_id, name, number: contact_id.replace(/@.+$/, '') }))
      .sort((a, b) => String(a.name).localeCompare(String(b.name)))
      .slice(0, 500),
    membership_requests: [...state.membershipRequests.values()]
      .sort((a, b) => String(b.received_at || '').localeCompare(String(a.received_at || ''))),
    qr_data_url: includeQr ? state.qrDataUrl : null,
    chats: [...state.chats.values()]
      .sort((a, b) => String(b.last_message_at || '').localeCompare(String(a.last_message_at || '')))
      .slice(0, 250),
  };
}

function rememberMessage(state, chatId, row) {
  const rows = state.messages.get(chatId) || [];
  if (row.message_id && rows.some(item => item.message_id === row.message_id)) return;
  rows.push(row);
  rows.sort((a, b) => String(a.occurred_at || '').localeCompare(String(b.occurred_at || '')));
  state.messages.set(chatId, rows.slice(-150));
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
  let name = patch.name || previous.name || state.contacts.get(jid) || jid.replace(/@.+$/, '');
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
}

async function processMessage(state, item) {
  const key = item?.key || {};
  if (!item?.message || !key.remoteJid || key.remoteJid === 'status@broadcast') return;
  const chatId = key.remoteJid;
  const isGroup = chatId.endsWith('@g.us');
  const senderJid = isGroup ? (key.participant || item.participant || '') : chatId;
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
      sender_name: item.pushName || state.contacts.get(senderJid) || senderJid.replace(/@.+$/, ''),
      received_at: receivedAt,
    });
    state.lastEventAt = new Date().toISOString();
    return;
  }
  rememberMessage(state, chatId, {
    message_id: String(key.id || `${Date.now()}`),
    from_me: Boolean(key.fromMe),
    sender_id: senderJid,
    sender_name: key.fromMe ? (state.identity?.name || 'Baiamonte') : (item.pushName || state.contacts.get(senderJid) || senderJid.replace(/@.+$/, '')),
    text: text || (media ? `[${media.type}]` : '[message]'),
    message_type: media?.type || 'text',
    occurred_at: receivedAt,
  });
  if (key.fromMe) return;
  const payload = {
    account_slot: state.slot,
    message_id: String(key.id || `${Date.now()}`),
    chat_id: chatId,
    chat_name: state.chats.get(chatId)?.name || chatId,
    is_group: isGroup,
    sender_id: senderJid,
    sender_name: item.pushName || state.contacts.get(senderJid) || senderJid.replace(/@.+$/, ''),
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
  state.state = 'connecting';
  state.error = null;
  state.qr = null;
  state.qrDataUrl = null;
  const authDir = path.join(DATA_ROOT, `account-${slot}`);
  await fs.mkdir(authDir, { recursive: true });
  const { state: authState, saveCreds } = await useMultiFileAuthState(authDir);
  const socket = makeWASocket({
    auth: authState,
    logger,
    printQRInTerminal: false,
    browser: ['Tenuta Baiamonte', 'Vineyard Operations', '1.0'],
    syncFullHistory: false,
    markOnlineOnConnect: false,
    generateHighQualityLinkPreview: false,
  });
  state.socket = socket;
  socket.ev.on('creds.update', saveCreds);
  socket.ev.on('contacts.upsert', rows => rows.forEach(row => {
    if (row.id) state.contacts.set(row.id, row.notify || row.name || row.verifiedName || row.id.replace(/@.+$/, ''));
  }));
  socket.ev.on('chats.upsert', rows => rows.forEach(row => updateChat(state, row.id, {
    name: row.name,
    last_message_at: row.conversationTimestamp ? new Date(Number(row.conversationTimestamp) * 1000).toISOString() : null,
  })));
  socket.ev.on('messaging-history.set', history => {
    (history.contacts || []).forEach(row => {
      if (row.id) state.contacts.set(row.id, row.notify || row.name || row.verifiedName || row.id.replace(/@.+$/, ''));
    });
    (history.chats || []).forEach(row => updateChat(state, row.id, { name: row.name }));
    (history.messages || []).forEach(item => {
      const key = item?.key || {};
      if (!item?.message || !key.remoteJid || key.remoteJid === 'status@broadcast') return;
      const chatId = key.remoteJid;
      const senderJid = chatId.endsWith('@g.us') ? (key.participant || item.participant || '') : chatId;
      const timestamp = Number(item.messageTimestamp || 0);
      const occurredAt = timestamp ? new Date(timestamp * 1000).toISOString() : new Date().toISOString();
      const text = cleanText(item.message).trim();
      const media = mediaInfo(item.message);
      updateChat(state, chatId, { last_message: text.slice(0, 180), last_message_at: occurredAt });
      rememberMessage(state, chatId, {
        message_id: String(key.id || `${timestamp}-${senderJid}`),
        from_me: Boolean(key.fromMe),
        sender_id: senderJid,
        sender_name: key.fromMe ? (state.identity?.name || 'Baiamonte') : (item.pushName || state.contacts.get(senderJid) || senderJid.replace(/@.+$/, '')),
        text: text || (media ? `[${media.type}]` : '[message]'),
        message_type: media?.type || 'text',
        occurred_at: occurredAt,
      });
    });
  });
  socket.ev.on('messages.upsert', async event => {
    if (event.type !== 'notify') return;
    for (const item of event.messages || []) {
      try { await processMessage(state, item); }
      catch (error) {
        state.error = String(error?.message || error).slice(0, 300);
        state.lastEventAt = new Date().toISOString();
      }
    }
  });
  socket.ev.on('connection.update', async update => {
    if (update.qr) {
      state.state = 'scan_qr';
      state.qr = update.qr;
      state.qrDataUrl = await QRCode.toDataURL(update.qr, { width: 360, margin: 2, color: { dark: '#10100f', light: '#fffdf4' } });
    }
    if (update.connection === 'open') {
      state.state = 'connected';
      state.qr = null;
      state.qrDataUrl = null;
      state.identity = {
        id: socket.user?.id || null,
        name: socket.user?.name || null,
      };
      state.error = null;
      state.lastEventAt = new Date().toISOString();
    }
    if (update.connection === 'close') {
      state.socket = null;
      const code = update.lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      state.state = loggedOut ? 'not_linked' : 'disconnected';
      state.error = loggedOut ? 'Account was logged out from WhatsApp.' : String(update.lastDisconnect?.error?.message || 'Connection closed').slice(0, 300);
      if (!loggedOut) state.reconnectTimer = setTimeout(() => startAccount(slot).catch(() => {}), 5000);
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

const app = express();
app.use(express.json({ limit: '1mb' }));
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
app.get('/accounts/:slot/chats/:chatId/messages', async (req, res) => {
  const slot = Number(req.params.slot);
  if (![1, 2].includes(slot)) return res.status(404).json({ error: 'Unknown account slot' });
  const state = accountState(slot);
  const chatId = decodeURIComponent(req.params.chatId);
  if (!state.chats.has(chatId) && state.contacts.has(chatId)) await updateChat(state, chatId, { name: state.contacts.get(chatId) });
  if (!state.chats.has(chatId)) return res.status(404).json({ error: 'Chat is not visible on this account' });
  res.json({ chat: state.chats.get(chatId), messages: (state.messages.get(chatId) || []).slice(-100) });
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
