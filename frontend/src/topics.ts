import type { Post, TopicColor } from "./types";

// Shared print inks for topic tags and trend series, in light/dark order.
export const TOPIC_INKS: Record<TopicColor, readonly [string, string]> = {
  red: ["#AE3824", "#D6553E"], navy: ["#2B5C8F", "#6D9ECE"],
  amber: ["#8C5A24", "#D49B42"], teal: ["#28666E", "#59A8B2"],
  purple: ["#6B4D82", "#A385C2"], rose: ["#A04462", "#D4708F"],
  slate: ["#54626F", "#9BA9B5"], brown: ["#70665C", "#B0A69A"],
  emerald: ["#2D6A4F", "#52B788"], indigo: ["#3F4E8C", "#8292DC"],
  coral: ["#C8553D", "#E88C78"], olive: ["#58641D", "#9FA865"],
  cyan: ["#1D6F8A", "#52ABC9"], wine: ["#7A2038", "#C45B77"],
  ochre: ["#996B1F", "#E2B056"], rust: ["#9E4324", "#DE7955"],
};
export function topicColor(key: string): string {
  const [light, dark] = TOPIC_INKS[key as TopicColor] ?? TOPIC_INKS.red;
  return `light-dark(${light}, ${dark})`;
}
export function filterTopicPosts(posts: Post[], topicId: number | null): Post[] {
  return topicId === null ? posts : posts.filter((p) => p.topic_ids?.includes(topicId));
}
