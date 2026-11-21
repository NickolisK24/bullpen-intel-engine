export default function HistoricalTransactions({ transactions, team, through }) {
  const source = transactions?.source
  const covered = transactions?.team === team && transactions.represented === through
    && transactions.coverage === 'retained_league_response' && source?.outcome === 'received' && source.reason === null && source.acquired_at
    && source.parameters?.sportId === 1 && source.parameters.startDate === through && source.parameters.endDate === through
    && ['available', 'partial'].includes(transactions.status) && Array.isArray(transactions.events)
    && transactions.events.every(event => event.transaction_date === through && event.transaction_key
      && [event.from_team_id, event.to_team_id].includes(team))
  return <section>
    <h3>Official pitcher transactions</h3>
    {!covered ? <p>Transaction evidence unavailable for {through}.</p> : <>
      {transactions.events.length > 0 ? <ul>{transactions.events.map(event =>
        <li key={event.transaction_key}>{event.description} Reported {event.transaction_date}.
          {event.effective_date && ` Effective ${event.effective_date}.`}</li>)}</ul>
        : <p>No qualified pitcher transaction for this club in the retained MLB response for {through}.</p>}
      {transactions.events.length > 0 && <details><summary>Transaction evidence</summary>
        <p>MLB transaction response acquired {transactions.source.acquired_at}.</p>
        <p className="break-all">Response digest {transactions.source.digest}</p>
      </details>}
      {transactions.status === 'partial' && <p>Some club records lack verified pitcher or roster evidence.</p>}
    </>}
  </section>
}
