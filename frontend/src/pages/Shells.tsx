import { useParams } from 'react-router-dom';
import { EmptyPanel } from '../components/Feedback.tsx';

export function Reviewer() {
  return <EmptyPanel eyebrow="Reviewer workspace" title="Make room for a closer look."><p>Review tasks and the evidence behind each finding will appear here once the review queue is connected.</p><span className="shell-tag">Review queue · coming next</span></EmptyPanel>;
}
export function Observe() {
  return <EmptyPanel eyebrow="Observability" title="Follow the work behind each finding."><p>Run timelines, resource use and the changes made by the agent will appear here when traces are connected.</p><span className="shell-tag">Run activity · awaiting connection</span></EmptyPanel>;
}
export function Receipt() {
  const { orderId } = useParams();
  return <EmptyPanel eyebrow="Evidence receipt" title="A record of what you saw."><p>The Passport at purchase and later source changes will appear here when receipts are connected.</p><span className="shell-tag">Receipt reference: {orderId}</span></EmptyPanel>;
}
export function NotFound() {
  return <EmptyPanel eyebrow="Page unavailable" title="This page could not be found."><p>Choose a workspace from the navigation above.</p></EmptyPanel>;
}
