"""Conservative physical identity and component suggestions from UT evidence."""
import json
import re
from fractions import Fraction
from .ut_defaults import defaults


def normalize(value):
    return ' '.join(str(value or '').upper().replace('"','').replace("'",'').split()).lstrip('#').strip()


def component(band):
    label=normalize(band)
    if label.isdigit() or label in {'S','PIPE','STRAIGHT','SPOOL'}:return 'straight_pipe','A106 B'
    if re.match(r'^(E(?:\s|$)|ELBOW\b|BEND\b)',label):return 'elbow','A234 WPB'
    if re.match(r'^(T(?:\s|$)|TEE\b|A$|B$|C$)',label):return 'tee','A234 WPB'
    if re.match(r'^(R(?:\s|$)|REDUCER\b)',label):return 'reducer','A234 WPB'
    if re.match(r'^(CAP|COUPLING|FITTING|BRANCH)\b',label):return 'fitting','A234 WPB'
    return 'unknown',None


def identity(reading,snapshot=None):
    loc=json.loads(reading.get('effective_location',reading.get('location_candidates','[]')))
    raw=json.loads(reading.get('location_candidates','[]'))
    source=defaults(snapshot or {},reading['cell'],loc[2] if len(loc)>2 else '')
    section=(source.get('segment') if loc[:1]==raw[:1] else None) or (loc[0] if loc else '')
    joint=normalize(loc[1] if len(loc)>1 else '')
    band=normalize(loc[2] if len(loc)>2 else '')
    band=re.sub(r'^TEE[- ](?=[ABC]$)','',band)
    size=normalize(reading.get('match_size_override') or source.get('nps'))
    if size:
        try:size=str(float(sum(Fraction(x) for x in size.split())))
        except (ValueError,ZeroDivisionError):pass
    return dict(section=normalize(section),joint=joint,band=band,size=size,
                component=component(band)[0],material=component(band)[1],
                position=tuple(normalize(x) for x in loc[3:]))


def key(evidence):
    if not all(evidence[k] for k in ('section','joint','band')):return None
    size=evidence['size']
    try:size=str(float(sum(Fraction(x) for x in size.split()))) if size else ''
    except (ValueError,ZeroDivisionError):pass
    band=re.sub(r'^TEE[- ](?=[ABC]$)','',normalize(evidence['band']))
    return (normalize(evidence['section']),normalize(evidence['joint']),band,size,*evidence['position'])
