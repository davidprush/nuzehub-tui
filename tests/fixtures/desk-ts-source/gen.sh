#!/bin/zsh
# Scratch: run the web's own TS functions (node type-stripping) on synthetic input and write fixtures + data.
set -e -o pipefail
W=/tmp/nzt020/web/src/lib/desk
F=/tmp/nzt020/fx
cd $F
for f in rank places gazetteer links; do
  /usr/bin/sed -E 's#"@/lib/desk/([a-z-]+)"#"./\1.ts"#g' $W/$f.ts > $F/$f.ts
done
/usr/bin/sed -E 's#"@/lib/desk/([a-z-]+)"#"./\1.ts"#g' $W/geo-clean.ts > $F/geo-clean.ts
# computeMapData + heatLevel verbatim from map-data.tsx (React provider parts left out)
{
  print 'import { countryById } from "./gazetteer.ts";'
  print 'import { linkKindLabel } from "./links.ts";'
  print 'import { articleFrom, countriesFor, type Placeable } from "./places.ts";'
  print 'import type { Country } from "./gazetteer.ts";'
  print 'type MapArticle = { url: string; title: string; countryId: string; lon: number; lat: number; source: string };'
  print 'type Story = { id: string; title: string; url: string; feedUrl: string; summary: string; publishedAt?: string };'
  /usr/bin/awk '/^export type MapLocation/{on=1} /^const MapContext/{on=0} on' $W/map-data.tsx | /usr/bin/grep -v 'FeedError\|feedStatus\|quotes: Quote\|tape: Quote'
  /usr/bin/awk '/^function sourceOf/{on=1} /^\/\*\* Computes the map picture/{on=0} on' $W/map-data.tsx
  /usr/bin/awk '/^\/\*\* 0..5 heat level/{on=1} on' $W/map-data.tsx
} > $F/mapdata.ts
node --experimental-strip-types --no-warnings $F/run.ts
