(()=>{
  function openFinanceMetricDetails(kind){
    const f=state.finance||{},documents=f.recent_documents||[],labor=f.labor_records||[],months=f.monthly||[],cash=f.cash||[];
    const documentRow=row=>`<div class="finance-document-row"><span class="list-icon">€</span><div><b>${esc(row.party_name||row.document_number||'Accounting document')}</b><small>${esc(row.document_number||'')} · ${row.document_date?new Date(`${String(row.document_date).slice(0,10)}T12:00:00`).toLocaleDateString():''} · ${esc(row.payment_status||row.status||'')}</small></div><strong>${eur(row.taxable_amount)}</strong>${row.id?`<button type="button" data-print-finance="${esc(row.id)}">View / print</button>`:''}</div>`;
    const laborRow=(row,value)=>`<div class="finance-document-row"><span class="list-icon">⌁</span><div><b>${esc(row.person_or_crew||'Labor')}</b><small>${row.work_date?new Date(`${String(row.work_date).slice(0,10)}T12:00:00`).toLocaleDateString():''} · ${esc(row.work_performed||row.role||'approved labor')} · ${esc(String(row.payment_status||'').replaceAll('_',' '))}</small></div><strong>${eur(value)}</strong></div>`;
    let title='',rows=[],summary='';
    if(kind==='revenue'){
      title=`${f.year||state.year} revenue`;rows=documents.filter(row=>row.document_type==='sales_invoice'&&row.status!=='void').map(documentRow);summary=`${eur(f.actual?.revenue)} net revenue from mirrored sales invoices.`;
    }else if(kind==='cost'){
      title=`${f.year||state.year} costs`;rows=documents.filter(row=>row.document_type==='purchase_invoice'&&row.status!=='void').map(documentRow);summary=`${eur(f.actual?.cost)} net cost from mirrored purchase invoices.`;
    }else if(kind==='result'){
      title=`${f.year||state.year} result`;rows=months.map(row=>`<div class="finance-review-row"><span><b>${new Date(2000,Number(row.fiscal_month)-1,1).toLocaleDateString(undefined,{month:'long'})}</b><small>${eur(row.actual_revenue)} revenue − ${eur(row.actual_cost)} cost</small></span><strong class="${Number(row.actual_result)<0?'negative':''}">${eur(row.actual_result)}</strong></div>`);summary=`${eur(f.actual?.revenue)} revenue − ${eur(f.actual?.cost)} costs = ${eur(f.actual?.result)} before tax.`;
    }else if(kind==='cash'){
      title='Recorded cash accounts';rows=cash.map(row=>`<div class="finance-review-row"><span><b>${esc(row.name||'Account')}</b><small>${esc(row.account_type||row.currency||'recorded balance')}</small></span><strong>${eur(row.current_balance)}</strong></div>`);summary=`${eur(cash.reduce((sum,row)=>sum+Number(row.current_balance||0),0))} across ${cash.length} recorded account${cash.length===1?'':'s'}.`;
    }else{
      const value=kind==='labor-cost'?row=>Number(row.labor_cost_eur||0)+Number(row.other_cost_eur||0):kind==='labor-paid'?row=>Number(row.amount_paid_eur||0):row=>Number(row.balance_due_eur||0);
      title=kind==='labor-cost'?`${f.year||state.year} labor cost`:kind==='labor-paid'?`${f.year||state.year} labor paid`:`${f.year||state.year} labor due`;
      rows=labor.filter(row=>value(row)>0).map(row=>laborRow(row,value(row)));
      summary=kind==='labor-cost'?'Approved labor and reimbursements by work record.':kind==='labor-paid'?'Ledger payments attached to the selected year’s approved work.':'Approved work still carrying an outstanding balance.';
    }
    $('recordDialogTitle').textContent=title;
    $('recordDialogList').innerHTML=`<p class="safety-note">${esc(summary)}</p>${rows.join('')||'<div class="empty">No supporting records for this total.</div>'}`;
    $('recordDialogList').querySelectorAll('[data-print-finance]').forEach(button=>button.onclick=()=>window.open(`api/v1/finance/documents/${encodeURIComponent(button.dataset.printFinance)}/print`,'_blank','noopener'));
    $('recordDialog').showModal();
  }

  document.querySelectorAll('[data-finance-detail]').forEach(card=>{
    card.onclick=()=>openFinanceMetricDetails(card.dataset.financeDetail);
    card.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();card.click()}};
  });
  window.openFinanceMetricDetails=openFinanceMetricDetails;
})();
