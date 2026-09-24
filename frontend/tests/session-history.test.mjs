import { test } from 'node:test';
import assert from 'node:assert/strict';
import { appendHistory, parseHistory } from '../lib/session-history.ts';
const entry = id => ({id: String(id), question: `Q${id}`, topK: 6, result: {answer: 'Answer', sources: [{source:'a.pdf',page:2}], retrieval: {top_k:6,distance_metric:'squared_l2',similarity_metric:'cosine',chunks:[{source:'a.pdf',page:2,rank:1,chunk_id:'c1',index_id:'i1',text:'Evidence',distance:0.2,similarity_score:0.9}]}}});
test('only latest ten snapshots survive, newest first, including original evidence and Top-K', () => {
 let history=[];
 for(let i=0;i<12;i++) history=appendHistory(history,entry(i));
 assert.deepEqual(history.map(x=>x.id),['11','10','9','8','7','6','5','4','3','2']);
 assert.deepEqual(parseHistory(JSON.stringify(history)),history);
 assert.deepEqual(parseHistory('[]'),[]);
});
test('malformed storage and corrupt nested evidence are rejected', () => {
 for(const raw of [null,'broken','{}','[null]',JSON.stringify([{...entry(1),topK:3}]),JSON.stringify([{...entry(1),result:{answer:'A',sources:[null]}}])]) assert.deepEqual(parseHistory(raw),[]);
 const broken=entry(2); broken.result.retrieval.chunks[0].distance='oops';
 assert.deepEqual(parseHistory(JSON.stringify([broken,entry(3)])),[entry(3)]);
});
