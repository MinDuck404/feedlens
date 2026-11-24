import { Check, Trash2 } from "lucide-react";
import { groupName } from "../../lib/logic";
import { useI18n } from "../../i18n";
import { PLATFORM_MODES, jobProfileSuggestions, sourceLines, type ModeDraft, type PlatformMode } from "../../lib/platformModes";
import type { JobProfile, Mode, Platform, SavedGroup } from "../../api/types";
import { Button, IconButton, Select, SegmentedControl, TextField } from "../../components/ui";
import { Group, Toggle } from "./Controls";

/** Link dán vào ô một dòng: tách theo dấu cách, xuống dòng hoặc dấu phẩy */
export const links = (t: string) => t.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);

/** Rút gọn link nhóm để dễ đọc: facebook.com/groups/vieclamit */
const shortUrl = (u: string) => u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");

interface Props {
  f: { platform: Platform };
  mode: Mode;
  definition: PlatformMode;
  usesSaved: boolean;
  myGroups: SavedGroup[];
  sources: string[];
  newGroups: string;
  setNewGroups: (value: string) => void;
  updateGroups: (list: SavedGroup[]) => void;
  addGroups: () => void;
  sourceText: string;
  setSourceText: (value: string) => void;
  draft: ModeDraft;
  setOption: (name: string, value: ModeDraft["options"][string]) => void;
  changeMode: (platform: Platform, mode: Mode) => void;
  jobProfile: JobProfile | null;
}

export function SourceMode({ f, mode, definition, usesSaved, myGroups, sources, newGroups, setNewGroups, updateGroups, addGroups, sourceText, setSourceText, draft, setOption, changeMode, jobProfile }: Props) {
  const { t } = useI18n();
  const hint = definition.fields.find((field) => field.name === "sources");
  return (
          <Group label={t("cmp.where")}>
            <SegmentedControl compact label={t("cmp.where")} value={mode} onChange={(v) => changeMode(f.platform, v as Mode)}
              options={[...PLATFORM_MODES[f.platform], ...(mode === "legacy_group" ? [definition] : [])].map((item) => ({ value: item.mode, label: t(item.label) }))} />
            <p className="mt-2 text-sm text-ink-soft">{t(definition.description)}</p>
            {f.platform === "facebook" && mode === "search" && <p className="mt-2 text-sm text-ink-soft">{t("cmp.notice.fbSearchLowResults")}</p>}
            {(f.platform === "reddit" || f.platform === "x") && <p role="note" className="mt-3 rounded-card bg-sunken p-3 text-xs text-ink-soft">{t(f.platform === "reddit" ? "cmp.warning.redditPolicy" : "cmp.warning.xPolicy")}</p>}

            {usesSaved && hint && (
              <div className="mt-3">
                {myGroups.length > 0 && (
                  <>
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                      <span>{t(hint.type === "saved" ? "cmp.groupsSelectedCount" : "cmp.sourcesSelectedCount", { selected: sources.length, total: myGroups.length })}</span>
                      <button type="button" className="interactive-tap min-h-10 text-link underline-offset-4 hover:underline"
                        onClick={() => updateGroups(myGroups.map((g) => ({ ...g, enabled: sources.length < myGroups.length })))}>
                        {sources.length < myGroups.length ? t("cmp.selectAll") : t("cmp.selectNone")}
                      </button>
                    </div>
                    <ul className="max-h-64 divide-y divide-line overflow-y-auto rounded-card border border-line">
                      {myGroups.map((g, i) => {
                        const name = mode === "list" ? g.url.replace(/\/$/, "").split("/").pop()! : groupName(g.url);
                        return (
                          <li key={g.url} className="group/row flex items-center transition-colors duration-[var(--duration-fast)] hover:bg-sunken/60">
                            <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 py-2.5">
                              <input type="checkbox" className="peer sr-only" checked={g.enabled}
                                onChange={(e) => updateGroups(myGroups.map((x, j) => j === i ? { ...x, enabled: e.target.checked } : x))} />
                              <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-sunken text-xs uppercase text-ink-soft
                                peer-checked:bg-primary peer-checked:text-primary-ink">
                                {name.slice(0, 2)}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-medium">{name}</span>
                                <span className="block truncate font-mono text-[11px] text-ink-soft" title={g.url}>{shortUrl(g.url)}</span>
                              </span>
                              <span aria-hidden className="grid size-5 shrink-0 place-items-center rounded-full border border-line text-transparent
                                peer-checked:border-primary peer-checked:bg-primary peer-checked:text-primary-ink peer-focus-visible:outline-2 peer-focus-visible:outline-accent">
                                <Check className="size-3" strokeWidth={3} />
                              </span>
                            </label>
                            <IconButton aria-label={t("cmp.removeGroup", { name })} title={t("cmp.removeFromList")}
                              onClick={() => updateGroups(myGroups.filter((_, j) => j !== i))}
                              className="mr-1 size-10 shrink-0 hover:text-danger">
                              <Trash2 className="size-4" />
                            </IconButton>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                )}
                {hint.type === "saved" ? <div className="mt-3 flex items-center gap-2 rounded-full border border-[var(--field-line)] bg-[var(--field-bg)] py-1 pr-1 pl-4 transition-[border-color,box-shadow] duration-[var(--duration-fast)] focus-within:border-accent focus-within:shadow-[0_0_0_2px_var(--accent-glow)]">
                  <input className="min-w-0 flex-1 bg-transparent py-1.5 text-sm border-0! outline-none! ring-0! [box-shadow:none]! focus-visible:outline-none! placeholder:text-ink-soft/70"
                    placeholder={myGroups.length ? t("cmp.pasteMore") : hint.example}
                    value={newGroups} onChange={(e) => setNewGroups(e.target.value)}
                    onKeyDown={(e) => { if (!e.nativeEvent.isComposing && e.key === "Enter") { e.preventDefault(); addGroups(); } }}
                    aria-label={t(hint.label)} />
                  <Button onClick={addGroups} disabled={!links(newGroups).length} variant="secondary" className="shrink-0 border-0! shadow-none! focus-visible:outline-none!">
                    {t("cmp.add")}
                  </Button>
                </div>
                : <div className="mt-3"><label className="block"><span className="mb-1.5 block text-sm">{t("cmp.onePerLine", { label: t(hint.label) })}</span>
                    <TextField as="textarea" className="resize-y" rows={3} value={newGroups} aria-label={t(hint.label)} placeholder={hint.placeholder ? t(hint.placeholder) : hint.example}
                      onChange={(event) => setNewGroups(event.target.value)} /></label><Button className="mt-2" variant="secondary" disabled={!sourceLines(newGroups).length} onClick={addGroups}>{t("cmp.add")}</Button></div>}
                {hint.type === "saved" && <p className="mt-1.5 px-1 text-xs text-ink-soft">{t("cmp.addHint")}</p>}
              </div>
            )}

            {hint?.type === "sources" && !usesSaved && (
              <label className="mt-3 block">
                <span className="mb-1 block text-sm">{t("cmp.onePerLine", { label: t(hint.label) })}</span>
                <TextField as="textarea" className="resize-y" rows={3} placeholder={hint.placeholder ? t(hint.placeholder) : hint.example} value={sourceText}
                  onChange={(e) => setSourceText(e.target.value)} aria-label={t(hint.label)} required={hint.required} />
              </label>
            )}
            {f.platform === "reddit" && mode === "subreddit" && <div className="mt-2 flex flex-wrap gap-2">
              {["r/forhire", "r/remotejs", "r/jobbit", "r/hiring"].map((sub) => <button key={sub} type="button"
                className="min-h-11 rounded-full border border-line px-3 text-xs text-ink-soft hover:border-ink"
                onClick={() => {
                  if (myGroups.some((source) => source.url === sub)) updateGroups(myGroups.map((source) => source.url === sub ? { ...source, enabled: true } : source));
                  else updateGroups([...myGroups, { url: sub, enabled: true }]);
                }}>+ {sub}</button>)}
            </div>}
            {definition.fields.filter((field) => field.name !== "sources").map((field) => {
              const value = draft.options[field.name];
              if (field.type === "toggle") return <div key={field.name} className="mt-3"><Toggle checked={value === true} onChange={(checked) => setOption(field.name, checked)}>{t(field.label)}</Toggle><p className="text-xs text-ink-soft">{t("cmp.input.groupChronologicalHint")}</p></div>;
              if (field.type === "multi") return <fieldset key={field.name} className="mt-4"><legend className="mb-2 text-sm">{t(field.label)}</legend><div className="flex flex-wrap gap-2">{field.choices?.map((choice) => {
                const checked = Array.isArray(value) && value.includes(choice.value);
                return <label key={choice.value} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line px-3 text-sm"><input type="checkbox" checked={checked}
                  onChange={() => setOption(field.name, checked ? (value as string[]).filter((item) => item !== choice.value) : [...(Array.isArray(value) ? value : []), choice.value])} />{t(choice.label)}</label>;
              })}</div></fieldset>;
              return <div key={field.name} className="mt-4"><label className="block"><span className="mb-1.5 block text-sm">{t(field.label)}</span>
                {field.type === "select" ? <Select aria-label={t(field.label)} value={value === null ? "" : String(value ?? "")} onChange={(event) => setOption(field.name, event.target.value || null)}>
                  {value === null && <option value="">{t("cmp.input.time.any")}</option>}{field.choices?.map((choice) => <option key={choice.value} value={choice.value}>{t(choice.label)}</option>)}
                </Select> : field.type === "number" ? <TextField type="number" min={field.min} max={field.max} step={1}
                  value={value === undefined || value === null ? "" : String(value)}
                  onChange={(event) => {
                    const raw = event.target.value;
                    setOption(field.name, raw === "" ? null : Number(raw));
                  }} /> : <TextField value={String(value ?? "")} required={field.required} maxLength={field.name === "keywords" ? 500 : 300}
                  placeholder={field.placeholder ? t(field.placeholder) : undefined} onChange={(event) => setOption(field.name, event.target.value)} />}</label>
                {field.hint && <p className="mt-1.5 text-xs text-ink-soft">{t(field.hint)}</p>}
                {mode === "jobs" && field.name === "keywords" && jobProfile && <div className="mt-2 flex flex-wrap gap-2">
                  {jobProfileSuggestions(jobProfile).map((role) => <button key={role} type="button"
                    className="min-h-10 max-w-full truncate rounded-full border border-line px-3 text-xs text-ink-soft hover:border-ink hover:text-ink"
                    title={role} onClick={() => setOption("keywords", role)}>{role}</button>)}
                </div>}
              </div>;
            })}
          </Group>
  );
}
