# i18n

`index.tsx` chứa provider, `useI18n`, `translate`, `serverMessage` và định dạng số; import `./i18n` trỏ vào đây.
Câu hiển thị nằm trong `locales/{vi,en,zh}/<namespace>.ts`; dòng đầu ghi màn hình/component dùng chúng.
Khi một câu sai, tìm key trong lời gọi `t("...")`, rồi mở namespace theo bảng tiền tố dưới đây:
- `common.ts`: `act`, `api`, `app`, `cat`, `lang`, `nav`, `prefs`, `source`, `status`, `theme`.
- `home.ts`: `home`; `sidebar.ts`: `sb`, `plat`; `history.ts`: `hist`; `auth.ts`: `login`.
- `run.ts`: `run`, `progress`, `posts`, `tab`; `jobs.ts`: `job`, `tier`; `composer.ts`: `cmp`, `kw`.
- `settings.ts`: `ck`, cài đặt chung/agent và `set.tab.*`; `keys.ts`: `set.key*`, key môi trường, lưu/kiểm tra key, model mặc định.
- `profile.ts`: `profile`; `topics.ts`: `topics`; `trends.ts`: `trends`; `ask.ts`: `ask`; `errors.ts`: `error`.
Ví dụ: `run.quotaReason.zero_quota` ở `locales/vi/run.ts`; `cmp.start` ở `locales/en/composer.ts`.
Thêm câu mới bằng cùng một key trong cùng namespace ở cả `vi`, `en`, `zh`; giữ giống tên và số lần xuất hiện placeholder như `{n}`.
Mỗi key chỉ có một nơi trong một ngôn ngữ. Nếu thêm namespace, thêm import và spread vào cả ba `locales/<lang>/index.ts`.
`locales/vi/index.ts` định nghĩa `Key`; hai ngôn ngữ còn lại dùng `Record<Key, string>` để phát hiện thiếu key khi build.
Kiểm trong `frontend/`: `npm run build` và `node --test tests/*.test.cjs`; test kiểm mọi file, tập key từng namespace, placeholder và key trùng.
