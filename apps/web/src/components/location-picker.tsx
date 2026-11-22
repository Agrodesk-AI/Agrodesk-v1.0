"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { apiJson } from "@/lib/api";
import { Input } from "@/components/ui/input";
import type { Place } from "@/lib/types";

export interface LocationValue {
  tehsil_id: number | null;
  village_id: number | null;
}

function fetchInto(path: string, set: (v: Place[]) => void): () => void {
  let live = true;
  apiJson
    .get<Place[]>(path)
    .then((v) => live && set(v))
    .catch(() => live && set([]));
  return () => {
    live = false;
  };
}

const selectCls =
  "h-12 w-full rounded-xl border border-border bg-surface px-3 text-base outline-none focus:border-primary disabled:opacity-50";

/** State → district → tehsil (required) → village (optional, searchable).
 *  Names come back in `lang`, falling back to English. */
export function LocationPicker({
  lang,
  onChange,
}: {
  lang: string;
  onChange: (v: LocationValue) => void;
}) {
  const t = useTranslations("location");
  const [states, setStates] = useState<Place[]>([]);
  const [districts, setDistricts] = useState<Place[]>([]);
  const [tehsils, setTehsils] = useState<Place[]>([]);
  const [villages, setVillages] = useState<Place[]>([]);
  const [stateId, setStateId] = useState<number | null>(null);
  const [districtId, setDistrictId] = useState<number | null>(null);
  const [tehsilId, setTehsilId] = useState<number | null>(null);
  const [village, setVillage] = useState<Place | null>(null);
  const [q, setQ] = useState("");

  const qs = `lang=${encodeURIComponent(lang)}`;

  // Each loader drops its response if inputs changed meanwhile, so a slow
  // lang=en reply can't overwrite a newer lang=hi one.
  useEffect(() => fetchInto(`/v1/locations/states?${qs}`, setStates), [qs]);

  useEffect(() => {
    if (!stateId) return setDistricts([]);
    return fetchInto(`/v1/locations/states/${stateId}/districts?${qs}`, setDistricts);
  }, [stateId, qs]);

  useEffect(() => {
    if (!districtId) return setTehsils([]);
    return fetchInto(`/v1/locations/districts/${districtId}/tehsils?${qs}`, setTehsils);
  }, [districtId, qs]);

  useEffect(() => {
    if (!tehsilId) return setVillages([]);
    let cancel: (() => void) | undefined;
    const handle = setTimeout(() => {
      const query = q.trim() ? `&q=${encodeURIComponent(q.trim())}` : "";
      cancel = fetchInto(
        `/v1/locations/villages?tehsil_id=${tehsilId}&limit=30${query}&${qs}`,
        setVillages,
      );
    }, 250);
    return () => {
      clearTimeout(handle);
      cancel?.();
    };
  }, [tehsilId, q, qs]);

  useEffect(() => {
    onChange({ tehsil_id: tehsilId, village_id: village?.id ?? null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tehsilId, village]);

  const num = (v: string) => (v ? Number(v) : null);

  return (
    <div className="space-y-3">
      <select
        className={selectCls}
        value={stateId ?? ""}
        onChange={(e) => {
          setStateId(num(e.target.value));
          setDistrictId(null);
          setTehsilId(null);
          setVillage(null);
        }}
        data-testid="loc-state"
      >
        <option value="">{t("state")}</option>
        {states.map((s) => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </select>
      <select
        className={selectCls}
        value={districtId ?? ""}
        disabled={!stateId}
        onChange={(e) => {
          setDistrictId(num(e.target.value));
          setTehsilId(null);
          setVillage(null);
        }}
        data-testid="loc-district"
      >
        <option value="">{t("district")}</option>
        {districts.map((d) => (
          <option key={d.id} value={d.id}>{d.name}</option>
        ))}
      </select>
      <select
        className={selectCls}
        value={tehsilId ?? ""}
        disabled={!districtId}
        onChange={(e) => {
          setTehsilId(num(e.target.value));
          setVillage(null);
          setQ("");
        }}
        data-testid="loc-tehsil"
      >
        <option value="">{t("tehsil")}</option>
        {tehsils.map((x) => (
          <option key={x.id} value={x.id}>{x.name}</option>
        ))}
      </select>
      {tehsilId && (
        <div className="space-y-2">
          {village ? (
            <div className="flex items-center justify-between rounded-xl border border-primary bg-primary/10 px-3 py-2 text-sm">
              <span>{village.name}</span>
              <button type="button" className="text-muted hover:underline" onClick={() => setVillage(null)}>
                {t("change")}
              </button>
            </div>
          ) : (
            <>
              <Input
                placeholder={t("villageSearch")}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                data-testid="loc-village-q"
              />
              {villages.length > 0 && (
                <ul className="max-h-48 overflow-auto rounded-xl border border-border">
                  {villages.map((v) => (
                    <li key={v.id}>
                      <button
                        type="button"
                        onClick={() => setVillage(v)}
                        className="w-full px-3 py-2 text-left text-sm hover:bg-black/5"
                      >
                        {v.name}
                        {v.name !== v.name_en && <span className="ml-2 text-xs text-muted">{v.name_en}</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-muted">{t("villageOptional")}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
