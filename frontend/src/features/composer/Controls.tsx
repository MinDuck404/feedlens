import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { useI18n } from "../../i18n";
import { IconButton, Select } from "../../components/ui";

export function ModelPicker({ provider, value, onChange }: { provider: string; value: string; onChange: (m: string) => void }) {
  const [models, setModels] = useState<string[]>([]);
  const [def, setDef] = useState("");
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");
  const { t } = useI18n();
  const requestId = useRef(0);

  const load = (refresh = false) => {
    const id = ++requestId.current;
    setState("loading");
    api.models(provider, refresh)
      .then((r) => { if (id !== requestId.current) return; setModels(r.models); setDef(r.default); setState("ok"); })
      .catch((e) => { if (id !== requestId.current) return; setError((e as Error).message); setState("error"); });
  };
  useEffect(() => { load(); return () => { ++requestId.current; }; }, [provider]);

  return (
    <div className="mt-2 flex gap-2">
      <Select value={value} onChange={(e) => onChange(e.target.value)}
        disabled={state !== "ok"} aria-label={t("cmp.modelAria")}>
        <option value="">
          {state === "loading" ? t("cmp.modelsLoading") : state === "error" ? error : t("cmp.modelDefault", { m: def })}
        </option>
        {value && !models.includes(value) && <option value={value}>{value}</option>}
        {models.map((m) => <option key={m} value={m}>{m}</option>)}
      </Select>
      <IconButton onClick={() => load(true)} aria-label={t("cmp.reloadModels")} variant="outline" busy={state === "loading"} className="size-11 shrink-0">
        <RefreshCw className="size-4" />
      </IconButton>
    </div>
  );
}

export function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-3 text-sm font-semibold tracking-tight">{label}</legend>
      {children}
    </fieldset>
  );
}

export function Toggle({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-4 py-2 text-sm">
      <span>{children}</span>
      <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span aria-hidden className="relative h-5 w-9 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-primary peer-focus-visible:outline-2 peer-focus-visible:outline-accent
        after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-surface after:transition-transform after:duration-[var(--duration-fast)] motion-reduce:after:transition-none peer-checked:after:translate-x-4" />
    </label>
  );
}
