"""Order-independent, conservative public geographic hierarchy matching."""
from .assistant_places import normalize, forms
from . import weather, geocoding

RANK = {'state': 0, 'county': 5, 'administrative': 5, 'municipality': 10,
        'lake': 10, 'water': 10, 'city': 15, 'town': 20, 'village': 30,
        'suburb': 35, 'quarter': 35, 'neighbourhood': 40, 'hamlet': 40,
        'isolated_dwelling': 45, 'pier': 50}


def compatible(point, region):
    address = point.get('address', {})
    box = region.get('bbox')
    inside = False
    if box:
        south,north,west,east = box
        inside = south-.025 <= point['latitude'] <= north+.025 and west-.025 <= point['longitude'] <= east+.025
        if not inside:
            return False
    # An explicit contradictory administrative name beats a broad bounding box.
    keys = {'town': ('town','city'), 'city': ('town','city'),
            'municipality': ('municipality',), 'county': ('county',), 'state': ('state',)}
    known = [address[k] for k in keys.get(region.get('type'), ()) if k in address]
    if known and not any(normalize(v) == normalize(region['name']) for v in known):
        return False
    for key in ('town', 'city', 'municipality'):
        if key in address and key in region.get('address', {}) and normalize(address[key]) != normalize(region['address'][key]):
            return False
    if any(normalize(region['name']) == normalize(v) for v in address.values()):
        return True
    # A small shoreline margin, rather than the old 100 km proximity check.
    return inside


def unique(rows):
    found=[]
    for row in rows:
        if not any(normalize(row['name']) == normalize(r['name']) and weather.distance(
                (row['latitude'],row['longitude']), (r['latitude'],r['longitude'])) < 1 for r in found):
            found.append(row)
    return found


def candidates(surface, metadata=False):
    from .assistant_location import name_candidates, RESOLUTION_DEADLINE
    import time
    found=[]
    for name in name_candidates(surface):
        if RESOLUTION_DEADLINE.get() is not None and time.monotonic() >= RESOLUTION_DEADLINE.get():
            return []
        try:
            row=weather.resolve_place(name)
            canonical=row['name'].split(' (',1)[0]
            if normalize(surface) in forms(canonical) and 59 <= row['latitude'] <= 71 and 19 <= row['longitude'] <= 32:
                found.append({'name':canonical,'latitude':row['latitude'],'longitude':row['longitude'],'provider':'fmi'})
                break
        except weather.WeatherError:
            continue
    geocoding.report('fmi',len(found),'name_verified' if found else 'no_matching_candidates',False)
    if found and not metadata:
        return unique(found)
    external=[]
    for name in name_candidates(surface):
        if RESOLUTION_DEADLINE.get() is not None and time.monotonic() >= RESOLUTION_DEADLINE.get():
            return []
        external.extend(r for r in geocoding.lookup_all(name) if normalize(surface) in forms(r['name']))
        if external:
            break
    return unique(external) if external else unique(found)


def pair(first, second):
    from .assistant_location import PlaceAmbiguity
    groups=[candidates(first),candidates(second)]
    # FMI has no hierarchy metadata. Fetch it only where comparison needs it.
    initial = list(groups)
    for index,surface in enumerate((first,second)):
        unknown = groups[index] and all(r.get('type') not in RANK for r in groups[index])
        broad_other = any(0 <= RANK.get(r.get('type'),-1) <= 20 for r in initial[1-index])
        if unknown and not broad_other:
            groups[index] = candidates(surface,True)
    accepted=[]
    for points,regions in (groups,groups[::-1]):
        for point in points:
            for region in regions:
                p_rank=RANK.get(point.get('type'),40 if point.get('provider')=='fmi' else -1)
                r_rank=RANK.get(region.get('type'),-1)
                if point.get('type') not in RANK and r_rank > 20:
                    continue  # An untyped FMI point does not prove a finer place class.
                if p_rank > r_rank >= 0 and compatible(point,region):
                    accepted.append(point)
    accepted=unique(accepted)
    geocoding.report('hierarchy',len(accepted),'accepted' if len(accepted)==1 else 'municipality_required',True)
    if len(accepted)!=1:
        raise PlaceAmbiguity('Paikkaa ei voitu erottaa varmasti. Lisää kysymykseen tarkemman paikan kunta.')
    return accepted[0]
