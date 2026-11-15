import { TOPIC_INKS, topicColor } from "./topics";
import type { TopicColor } from "./types";

export function trendColor(hex: string): string {
  const key = (Object.keys(TOPIC_INKS) as TopicColor[]).find((key) => TOPIC_INKS[key][0].toLowerCase() === hex.toLowerCase());
  return key ? topicColor(key) : "var(--ink-soft)";
}
export function trendPoints(counts: number[], width: number, height: number, max: number) {
  return counts.map((value, index) => ({
    x: counts.length <= 1 ? width / 2 : index / (counts.length - 1) * width,
    y: height * (1 - Math.max(0, Math.min(max, value)) / Math.max(1, max)),
  }));
}
export function trendPath(points: { x: number; y: number }[]): string {
  return points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
}
