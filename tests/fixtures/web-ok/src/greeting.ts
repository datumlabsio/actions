export function greeting(name: string): string {
  const trimmed = name.trim();
  if (trimmed.length === 0) {
    return "Hello, there";
  }
  return `Hello, ${trimmed}`;
}
