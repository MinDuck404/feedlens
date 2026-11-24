// Gộp các namespace tiếng Trung, kiểm tập key theo tiếng Việt.
import type { Key } from "../vi";
import { common } from "./common";
import { home } from "./home";
import { sidebar } from "./sidebar";
import { run } from "./run";
import { jobs } from "./jobs";
import { composer } from "./composer";
import { settings } from "./settings";
import { keys } from "./keys";
import { profile } from "./profile";
import { topics } from "./topics";
import { trends } from "./trends";
import { ask } from "./ask";
import { history } from "./history";
import { auth } from "./auth";
import { errors } from "./errors";

export const zh: Record<Key, string> = {
  ...common,
  ...home,
  ...sidebar,
  ...run,
  ...jobs,
  ...composer,
  ...settings,
  ...keys,
  ...profile,
  ...topics,
  ...trends,
  ...ask,
  ...history,
  ...auth,
  ...errors,
};
