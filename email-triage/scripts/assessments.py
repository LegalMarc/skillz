#!/usr/bin/env python3
"""Structured, private and invalidation-aware assessment cache helpers."""
import argparse
import hashlib
import json
from pathlib import Path

from history import assessment_cache_decision, get_cached_assessment, invalidate_assessments, record_assessment
from review import read_json, require


def fingerprint(content_digest, rules_digest, thread_digest, correction_version='0'):
    """Bind a decision to content, current rules, thread context and corrections."""
    values=[content_digest,rules_digest,thread_digest,str(correction_version)]
    require(all(isinstance(x,str) and x for x in values),'All assessment inputs must be explicit')
    return hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest()


def put(database, assessment):
    fields={'run_id','identity','assessed_at','rules_digest','content_digest','thread_digest','deadline','evidence','result','correction_version'}
    require(isinstance(assessment,dict) and set(assessment)==fields,'Invalid assessment fields')
    fp=fingerprint(assessment['content_digest'],assessment['rules_digest'],assessment['thread_digest'],assessment['correction_version'])
    record_assessment(database,assessment['run_id'],assessment['identity'],fingerprint=fp,
      assessed_at=assessment['assessed_at'],rules_digest=assessment['rules_digest'],content_digest=assessment['content_digest'],
      thread_digest=assessment['thread_digest'],correction_version=assessment['correction_version'],deadline=assessment['deadline'],evidence=assessment['evidence'],result=assessment['result'])
    return fp


def get(database,run_id,identity,*,content_digest,rules_digest,thread_digest,correction_version='0',now=None):
    fp=fingerprint(content_digest,rules_digest,thread_digest,correction_version)
    return get_cached_assessment(database,run_id,identity,fingerprint=fp,rules_digest=rules_digest,
      content_digest=content_digest,thread_digest=thread_digest,now=now)


def invalidate_for_change(database,run_id,identity,reason,at=None):
    """Call for a thread reply, rules edit, deadline reassessment or user correction."""
    allowed={'thread_reply','rules_changed','deadline_approaching','user_correction','content_changed'}
    require(reason in allowed,'Unsupported invalidation reason')
    invalidate_assessments(database,run_id,identity,reason,at)


def readiness(database,snapshot,rules_digest,current_evidence,now=None):
    """Return explicit cache readiness; missing fingerprints always mean reassessment."""
    require(isinstance(current_evidence,dict),'Current evidence map required')
    result=[]
    for row in snapshot['records']:
        identity={'account':row['account'],'message_id':row['message_id'],'current_id':row['current_id']}
        evidence=current_evidence.get(row['item'])
        if not isinstance(evidence,dict) or set(evidence)!={'account','message_id','current_id','content_digest','thread_digest','correction_version'} or any(evidence.get(k)!=identity[k] for k in identity):
            decision={'status':'awaiting_assessment','reason':'missing_current_evidence'}
        else:
            decision=assessment_cache_decision(database,snapshot['run_id'],identity,rules_digest=rules_digest,
              content_digest=evidence['content_digest'],thread_digest=evidence['thread_digest'],correction_version=evidence['correction_version'],now=now)
        result.append({'item':row['item'],**identity,'status':decision['status'],'reason':decision['reason']})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',required=True);p.add_argument('--run-id',required=True);p.add_argument('--identity',required=True,help='JSON object: account, message_id, current_id')
    p.add_argument('--content-digest',required=True);p.add_argument('--rules-digest',required=True);p.add_argument('--thread-digest',required=True)
    p.add_argument('--correction-version',default='0');p.add_argument('--now');a=p.parse_args()
    result=get(a.database,a.run_id,json.loads(a.identity),content_digest=a.content_digest,rules_digest=a.rules_digest,thread_digest=a.thread_digest,correction_version=a.correction_version,now=a.now)
    print(json.dumps(result,indent=2) if result else 'No reusable assessment; reassess evidence.')

if __name__=='__main__':main()
