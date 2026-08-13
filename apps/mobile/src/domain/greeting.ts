const shanghaiHour = new Intl.DateTimeFormat("en-US", {
  hour: "2-digit",
  hourCycle: "h23",
  timeZone: "Asia/Shanghai",
});

export function shanghaiGreeting(now: Date, name: string): string {
  const hour = Number(shanghaiHour.format(now));
  const salutation =
    hour < 5
      ? "夜深了"
      : hour < 12
        ? "早上好"
        : hour < 14
          ? "中午好"
          : hour < 18
            ? "下午好"
            : "晚上好";
  return `${salutation}，${name}`;
}
