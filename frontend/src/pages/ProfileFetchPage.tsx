import SubscriptionPanel from "../components/app/SubscriptionPanel";

/** 主页抓取页：订阅模式（原手动抓取已下线，统一走订阅） */
export default function ProfileFetchPage() {
  return (
    <div className="flex flex-col h-full">
      <SubscriptionPanel />
    </div>
  );
}
