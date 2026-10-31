import { useCallback, useState } from 'react';
import type { ApiClient } from '../api/client.ts';
import type { GraphResponse, SearchResponse } from '../types.ts';
import { usePoll } from '../usePoll.ts';
import { ErrorNotice } from './Feedback.tsx';
import { highlightExcerpt } from '../evidence.ts';
import { text } from '../glassbox.ts';

export function DependencyGraph({ graph }: { graph: GraphResponse }) {
  const names = new Map(graph.nodes.map((n) => [n.id, n]));
  return <div className="dependency-graph" aria-label="Source dependencies">{graph.edges.map((edge, index) => {
    const source = names.get(edge.source), target = names.get(edge.target);
    const stale = source?.status === 'REVOKED' || target?.status === 'STALE';
    return <div key={index} className={`dependency-edge ${stale ? 'dependency-stale' : ''}`}><span>{source?.label ?? edge.source}<small>{source?.status}</small></span><span aria-label={edge.relation}>{edge.relation === 'cites' ? 'cites →' : 'depends on →'}</span><span>{target?.label ?? edge.target}<small>{target?.status}</small></span></div>;
  })}{!graph.edges.length && <p>No dependencies recorded.</p>}</div>;
}
export function SearchResults({ result, query }: { result: SearchResponse; query: string }) {
  return <div><p>ranking only — no answer generated</p>{result.hits.map((hit, index) => <article className="search-hit" key={text(hit.passage_id) || index}><span className="plain-badge">{text(hit.source_label) || text(hit.source_version_id) || 'Source not recorded'}</span><p>{highlightExcerpt(text(hit.text), query).map((part, i) => part.highlighted ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>)}</p><p>Rank {index + 1} · {text(hit.passage_id)}</p></article>)}{!result.hits.length && <p>No matching passages.</p>}
    <details><summary>Ranking stages</summary>{Object.entries(result.stages).map(([stage, hits]) => <section key={stage}><h4>{stage}</h4><ol>{hits.map((hit, i) => <li key={i}>{text(hit.passage_id) || 'Passage not recorded'} · rank {text(hit.rank) || i + 1} · score {text(hit.score) || 'not recorded'}</li>)}</ol></section>)}</details></div>;
}
function Search({ api, caseId }: { api: ApiClient; caseId: string }) {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);
  return <section><h3>Ask the evidence</h3><form onSubmit={(event) => { event.preventDefault(); if (!query.trim() || pending) return; const q = query.trim(); setPending(true); setError(null); setResult(null); void api.searchEvidence(caseId, q).then((data) => { setSubmitted(q); setResult(data); }).catch((e: unknown) => setError(e instanceof Error ? e : new Error('Search could not be completed.'))).finally(() => setPending(false)); }}><label>Search stored passages<input value={query} onChange={(event) => setQuery(event.target.value)} /></label><button disabled={pending || !query.trim()}>{pending ? 'Searching…' : 'Search'}</button></form>{error && <ErrorNotice error={error} technical />}{result && <SearchResults result={result} query={submitted} />}</section>;
}
export function CaseExplorer({ api, caseId }: { api: ApiClient; caseId: string }) {
  const loadGraph = useCallback((signal: AbortSignal) => api.getGraph(caseId, signal), [api, caseId]);
  const loadChain = useCallback((signal: AbortSignal) => api.getChain(caseId, signal), [api, caseId]);
  const graph = usePoll(loadGraph, 30_000), chain = usePoll(loadChain, 30_000);
  return <section className="case-explorer"><Search key={caseId} api={api} caseId={caseId} /><h3>Dependencies and chain</h3>{graph.error && <ErrorNotice error={graph.error} technical />}{graph.data && <DependencyGraph graph={graph.data} />}{chain.error && <ErrorNotice error={chain.error} technical />}{chain.data && <p className="plain-badge">Chain {chain.data.valid ? 'valid' : 'broken'} · {chain.data.rows} rows · {chain.data.head?.slice(0, 12) ?? 'No head'}{chain.data.broken_at != null && ` · broken at ${chain.data.broken_at}`}</p>}</section>;
}
