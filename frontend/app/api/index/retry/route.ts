import { forward } from '../../../../lib/backend';
export async function POST() { return forward('/index/retry', { method: 'POST' }); }
