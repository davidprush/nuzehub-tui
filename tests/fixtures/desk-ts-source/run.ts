import { writeFileSync, readFileSync } from "node:fs";
import { rankStories, geopoliticalStories } from "./rank.ts";
import { detectCountries, norm } from "./places.ts";
import { COUNTRIES } from "./gazetteer.ts";
import { computeMapData, heatLevel } from "./mapdata.ts";
import { feature } from "/tmp/nzt020/web/node_modules/topojson-client/src/index.js";
import { cleanGeometry } from "./geo-clean.ts";

// Synthetic only: fictional outlets on .invalid hosts, invented headlines.
const NOW = Date.parse("2026-11-23T18:00:00.000Z");
const h = (hours: number) => new Date(NOW - hours * 36e5).toISOString();
const T: [string, string, string, string, number | null][] = [
  ["Ukraine and Poland agree new border crossing rules", "Officials in Kyiv and Warsaw met for talks.", "world", "a", 0.5],
  ["Ceasefire talks resume in Gaza", "Negotiators from Egypt and Qatar return to Cairo.", "world", "a", 1.2],
  ["Taiwan reports missile drills near its coast", "Taipei said China held exercises.", "world", "b", 3],
  ["Election results due in Brazil", "Counting continues in Sao Paulo and Brasilia.", "world", "b", 7],
  ["Tbilisi protests continue over election law", "Georgian opposition rallies in the capital.", "world", "a", 11],
  ["Atlanta, Georgia hosts tech summit", "Startups gather in the US state for a week.", "tech", "c", 13],
  ["Pyongyang tests a new rocket engine", "North Korea state media said the test was a success.", "world", "b", 20],
  ["Seoul markets rally on chip exports", "South Korea's exports rose for the ninth month.", "markets", "c", 26],
  ["Korea trade deal advances", "Negotiators met in a neutral venue.", "markets", "c", 30],
  ["Côte d’Ivoire cocoa harvest beats forecasts", "Abidjan exporters cite strong rains.", "markets", "a", 40],
  ["Iceland volcano alert raised again", "Reykjanes eruption risk climbs; Reykjavik airport open.", "world", "a", 50],
  ["Japan and Australia sign defence treaty", "Tokyo and Canberra deepen military ties.", "world", "b", 60],
  ["NATO summit opens in Brussels", "Allies discuss sanctions on Russia and support for Ukraine.", "world", "b", 70],
  ["Nuclear talks with Iran stall", "Tehran rejects new inspection terms.", "world", "a", 80],
  ["Wars of words: a history of diplomacy", "An essay on treaties through the ages.", "culture", "c", 95],
  ["Warfare game studio raises funds", "The studio in Sweden plans a sequel.", "tech", "c", 100],
  ["Mexico City braces for storm", "Forecasters warn of flooding in Mexico.", "world", "a", 110],
  ["Sponsored: best crypto picks", "Advertisement for crypto tokens.", "ads", "d", 2],
  ["Celebrity gossip roundup", "The week in celebrity news.", "gossip", "c", 4],
  ["India and Pakistan hold border talks", "New Delhi and Islamabad trade proposals.", "world", "b", 140],
  ["Old story about Peru mining", "Lima approves a copper mine.", "world", "a", 200],
  ["Undated feature on Kenya wildlife", "Nairobi park sees record visitors.", "world", "a", null],
  ["Saturn ring study published", "Cassini data revisited by researchers.", "space", "c", 5],
  ["Saturn rings younger than thought", "Cassini measurements suggest recent origin.", "space", "a", 5],
  ["Coup attempt reported in Niger", "Niamey airport closed; troops on streets.", "world", "b", 1.5],
  ["Airstrikes hit targets in Yemen", "Sanaa residents report explosions.", "world", "b", 0.2],
  ["Embargo on Venezuela oil eased", "Caracas welcomes the move.", "world", "a", 9],
  ["France and Germany plan joint jet", "Paris and Berlin sign an accord; UK watches.", "world", "c", 15],
];
const stories = T.map(([title, summary, feed, host, hours], i) => ({
  id: `fx-${i}`, title, summary, url: `https://${host}.example.invalid/${feed}/${i}`, feedUrl: `https://feeds.invalid/${feed}.xml`,
  publishedAt: hours === null ? "" : h(hours),
}));
const base = { sources: ["world", "tech", "markets", "culture", "space"].map((f, i) => ({ id: `s${i}`, name: `FX ${f}`, url: `https://feeds.invalid/${f}.xml`, enabled: true })),
  topics: [{ name: "Ukraine", weight: 5 }, { name: "chip exports", weight: 3 }, { name: "space science", weight: 12 }, { name: "x", weight: 2 }],
  boostKeywords: ["Saturn", ""], blockKeywords: ["Sponsored"], concerns: ["celebrity"], blockedHosts: ["www.d.example.invalid"] };
const votes = [
  { url: stories[22].url, title: stories[22].title, summary: stories[22].summary, vote: 1 },
  { url: "https://gone.invalid/1", title: "Rocket engine tests and missile drills", summary: "military exercises", vote: -1 },
];
const slim = (r: any[]) => r.map((s) => ({ id: s.id, score: s.score, taste: s.taste, hits: s.hits, sourceName: s.sourceName }));
const ranked: Record<string, unknown> = {};
for (const w of ["1", "3", "7", "all"] as const) ranked[w] = slim(rankStories(stories as any, base as any, w, NOW, votes as any));
const noVotes = slim(rankStories(stories as any, { ...base, topics: [], boostKeywords: [] } as any, "7", NOW, []));
const geo = geopoliticalStories(rankStories(stories as any, base as any, "7", NOW, votes as any)).map((s) => s.id);
const detect = stories.map((s) => detectCountries(s.title, s.summary).map((c) => c.iso2));
const links = [{ url: "https://x.com/fx/status/1", title: "Post about Lagos traffic", note: "Nigeria", author: "fx", kind: "x", at: h(1) }];
const placements = [{ url: stories[14].url, countryId: "250" }];
const archive = [{ url: "https://arch.invalid/1", title: "Archived Chile note", countryId: "152", lon: -70.67, lat: -33.45, source: "Article" },
  { url: stories[0].url, title: "dup", countryId: "804", lon: 30.52, lat: 50.45, source: "x" }];
const md = (m: any) => ({
  displayed: m.displayed, extras: m.extras, counts: [...m.counts.entries()], ranked: m.ranked.map((r: any) => [r.country.id, r.count]),
  maxCount: m.maxCount, locations: m.locations.map((l: any) => ({ key: l.key, countryId: l.countryId, urls: l.articles.map((a: any) => a.url), freshest: l.freshest })),
  arcs: m.arcs.map((a: any) => [a.key, a.count]), countryForUrl: [...m.countryForUrl.entries()],
});
const map = md(computeMapData(stories as any, links as any, placements, archive, false, NOW));
const mapPicture = md(computeMapData(stories as any, links as any, placements, archive, true, NOW));
const heat = Array.from({ length: 11 }, (_, i) => heatLevel(i));
const norms = ["Côte d’Ivoire", "São Tomé & Príncipe", "U.S.A. — news", "  Kyiv's   mayor "].map((s) => [s, norm(s)]);
writeFileSync("/tmp/nzt020/fx/ts-fixtures.json", JSON.stringify({ generatedBy: "web src/lib/desk rank.ts, places.ts, map-data.tsx (node --experimental-strip-types)",
  now: NOW, stories, prefs: base, votes, links, placements, archive, ranked, noVotes, geo, detect, map, mapPicture, heat, norms }, null, 1));
writeFileSync("/tmp/nzt020/fx/countries.json", JSON.stringify(COUNTRIES.map((c) => [c.id, c.iso2, c.name, c.lat, c.lon, c.aliases])));
const atlas = JSON.parse(readFileSync("/tmp/nzt020/web/node_modules/world-atlas/countries-110m.json", "utf8"));
const q = (v: number) => Math.round(v * 100) / 100;
const world = (feature(atlas, atlas.objects.countries) as any).features.filter((f: any) => f.id !== undefined && f.id !== null).map((f: any) => {
  const g = cleanGeometry(f.geometry) as any;
  if (!g) return null;
  const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  return [String(f.id), polys.map((p: any) => p.map((ring: any) => ring.map((pt: number[]) => [q(pt[0]), q(pt[1])])))];
}).filter(Boolean);
writeFileSync("/tmp/nzt020/fx/world110m.json", JSON.stringify(world));
console.log("stories", stories.length, "ranked7", (ranked["7"] as any[]).length, "geo", geo.length, "countries", COUNTRIES.length, "world", world.length);
