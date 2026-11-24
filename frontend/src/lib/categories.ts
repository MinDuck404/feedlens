// Mỗi loại bài có một màu cố định, dùng ở thanh phân loại, chấm màu, viền bài viết.
// Bảng màu "mực in" cho vibe Paper: đậm vừa, hơi trầm, đọc rõ trên cả nền giấy lẫn nền mực.
export const CATEGORY_COLOR: Record<string, string> = {
  job: "#1f7a4d",
  news: "#2f5fb3",
  tech: "#6a4fc4",
  marketplace: "#c2477a",
  question: "#0f8a95",
  event: "#b7851a",
  promotion: "#ff5a36",
  personal: "#8a8578",
  entertainment: "#9a9622",
  other: "#b3aea3",
};

export const colorOf = (c: string) => CATEGORY_COLOR[c] ?? CATEGORY_COLOR.other;

export const PLATFORM_LABEL: Record<string, string> = {
  facebook: "Facebook",
  linkedin: "LinkedIn",
  x: "X",
  reddit: "Reddit",
};
