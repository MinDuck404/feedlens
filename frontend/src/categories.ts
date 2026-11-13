// Mỗi loại bài có một màu cố định, dùng ở thanh phân loại, chấm màu, viền bài viết.
// Tông trung tính độ sáng vừa phải để đọc được trên cả nền sáng lẫn tối.
export const CATEGORY_COLOR: Record<string, string> = {
  job: "#1f9d6b",
  news: "#3b73e0",
  tech: "#7a5bdc",
  marketplace: "#d4537e",
  question: "#13a0ad",
  event: "#c8901a",
  promotion: "#e06a3c",
  personal: "#8a97ab",
  entertainment: "#b8b021",
  other: "#a3adba",
};

export const colorOf = (c: string) => CATEGORY_COLOR[c] ?? CATEGORY_COLOR.other;

export const PLATFORM_LABEL: Record<string, string> = {
  facebook: "Facebook",
  linkedin: "LinkedIn",
  x: "X",
  reddit: "Reddit",
};
