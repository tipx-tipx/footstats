import { NextResponse } from "next/server";

import { sekretyRowne } from "@/lib/auth";
import { readAppData, writeAppData } from "@/lib/appDataWrite";

/**
 * PING Z ZEWNĄTRZ, KTÓRY ODPALA CYKL PIPELINE'U.
 *
 * PO CO — zmierzone 2026-08-05 na 100 przebiegach z API GitHuba (okno 183 h):
 *
 *     cycle.yml deklaruje cron co 15 min   tyknięć powinno ~732, GitHub UTWORZYŁ 99 = 14%
 *     odstęp utworzeń: mediana 96 min, p90 183, max 227
 *     czekanie w kolejce: 0,0 min  <- concurrency NIC nie blokuje
 *
 * Minuty odpaleń są rozrzucone po całej godzinie (0, 1, 2, 4, 7 ... 59), a
 * cron co 15 minut może trafiać wyłącznie w :00/:15/:30/:45 — czyli to GitHub przesuwa
 * i gubi tyknięcia, nie my. Zdarzenie `schedule` jest u nich best-effort
 * i pierwsze idzie pod nóż przy obciążeniu Actions. `workflow_dispatch` NIE
 * jest tak traktowany: odpala od razu.
 *
 * Ta trasa jest więc prawdziwym zegarem produktu, a cron w `cycle.yml` zostaje
 * wyłącznie jako siatka bezpieczeństwa na wypadek, gdyby zewnętrzny pinger
 * padł. Nie usuwać go z tego powodu.
 *
 * KONFIGURACJA (Vercel → Environment Variables):
 *   TICK_SECRET       wymagany; bez niego trasa oddaje 503 i nic nie robi
 *   GH_DISPATCH_TOKEN fine-grained PAT z uprawnieniem Actions: write (już jest,
 *                     używa go /api/kupon-pomin)
 *   TICK_MIN_ODSTEP_S opcjonalny, domyślnie 1200 (20 min)
 *
 * Wołać: GET /api/tick?klucz=<TICK_SECRET>  (albo nagłówek Authorization:
 * Bearer <TICK_SECRET>, gdy zewnętrzna usługa umie nagłówki — wtedy sekret nie
 * ląduje w logach po drodze).
 */

const GH_REPO = process.env.GH_REPO ?? "tipx-tipx/footstats";
const GH_WORKFLOW = "cycle.yml";
const GH_REF = process.env.GH_REF ?? "master";

/**
 * ODSTĘP JEST PILNOWANY TUTAJ, NIE W USTAWIENIACH PINGERA.
 *
 * Zewnętrzna usługa może bić choćby co minutę — prawdziwy harmonogram siedzi
 * w kodzie, który podlega review i jedzie z deployem. Inaczej realna
 * częstotliwość produktu mieszkałaby w cudzym panelu, do którego nikt nie
 * zagląda; dokładnie ta klasa błędu co front trzymający kopię konfiguracji
 * backendu.
 *
 * 20 minut, bo cykl trwa dziś 32 min (mediana 05.08). Krócej nie ma sensu:
 * przebieg i tak czekałby na poprzedni, a my mielibyśmy tylko więcej ruchu
 * u źródeł (Superbet/365/statshub), które celowo oszczędzamy.
 */
const MIN_ODSTEP_S = Number(process.env.TICK_MIN_ODSTEP_S ?? 1200);
const KLUCZ_STANU = "cykl_dispatch"; // ten sam, którego pilnuje /api/kupon-pomin

function podanySekret(req: Request): string {
  const auth = req.headers.get("authorization") ?? "";
  if (auth.toLowerCase().startsWith("bearer ")) return auth.slice(7).trim();
  return new URL(req.url).searchParams.get("klucz") ?? "";
}

async function tick(req: Request) {
  const sekret = process.env.TICK_SECRET;
  if (!sekret) {
    return NextResponse.json(
      { ok: false, powod: "brak TICK_SECRET — trasa wyłączona" },
      { status: 503 },
    );
  }
  if (!sekretyRowne(podanySekret(req), sekret)) {
    // bez szczegółów: cudzy skaner ma się dowiedzieć wyłącznie „nie"
    return NextResponse.json({ ok: false }, { status: 401 });
  }

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) {
    return NextResponse.json(
      { ok: false, powod: "brak GH_DISPATCH_TOKEN" },
      { status: 503 },
    );
  }
  const supaUrl = process.env.SUPABASE_URL?.replace(/\/$/, "");
  const supaKey = process.env.SUPABASE_SERVICE_KEY;

  const naglowkiGh = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "footstats-tick",
  };
  const now = Math.floor(Date.now() / 1000);

  // 1. ODSTĘP. Stan trzymamy w Supabase, bo instancje serverless nie mają
  //    wspólnej pamięci — zmienna w module resetuje się co zimny start.
  if (supaUrl && supaKey) {
    const stan = await readAppData(supaUrl, supaKey, KLUCZ_STANU);
    const ostatni = typeof stan.ts === "number" ? stan.ts : 0;
    const minelo = now - ostatni;
    if (minelo < MIN_ODSTEP_S) {
      return NextResponse.json({
        ok: true,
        odpalono: false,
        powod: "za wcześnie",
        za_ile_s: MIN_ODSTEP_S - minelo,
      });
    }
  }

  // 2. CZY COŚ JUŻ CHODZI. `concurrency` w cycle.yml i tak nie przepuści
  //    drugiego przebiegu, ale przebieg czekający w kolejce zostaje
  //    ANULOWANY, gdy przyjdzie kolejny — i pojawia się w historii jako
  //    `cancelled`. Diagnozując cron 05.08 spędziliśmy czas na ustalaniu,
  //    czy te anulowania to awaria, czy nie. Nie produkujmy ich sami.
  try {
    const res = await fetch(
      `https://api.github.com/repos/${GH_REPO}/actions/workflows/${GH_WORKFLOW}` +
        `/runs?status=in_progress&per_page=1`,
      { headers: naglowkiGh, cache: "no-store" },
    );
    if (res.ok) {
      const dane = (await res.json()) as { total_count?: number };
      if ((dane.total_count ?? 0) > 0) {
        return NextResponse.json({
          ok: true,
          odpalono: false,
          powod: "cykl już chodzi",
        });
      }
    }
  } catch {
    // nie udało się sprawdzić — lecimy dalej; gorzej nie będzie niż dziś
  }

  // 3. ODPAL
  const res = await fetch(
    `https://api.github.com/repos/${GH_REPO}/actions/workflows/${GH_WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: { ...naglowkiGh, "Content-Type": "application/json" },
      body: JSON.stringify({ ref: GH_REF }),
    },
  );
  if (!res.ok) {
    return NextResponse.json(
      { ok: false, odpalono: false, powod: `GitHub ${res.status}` },
      { status: 502 },
    );
  }
  if (supaUrl && supaKey) {
    await writeAppData(supaUrl, supaKey, KLUCZ_STANU, { ts: now });
  }
  return NextResponse.json({ ok: true, odpalono: true });
}

// GET, bo tak wołają darmowe pingery (cron-job.org, UptimeRobot). POST dla
// tych, które umieją tylko jego.
export async function GET(req: Request) {
  return tick(req);
}
export async function POST(req: Request) {
  return tick(req);
}
