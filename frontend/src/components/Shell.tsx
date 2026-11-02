import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

export type AppTab = 'room' | 'match' | 'persona' | 'community' | 'plans' | 'all';

type AppShellProps = {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  showBack?: boolean;
  onBack?: () => void;
  activeTab?: AppTab;
  enabledTabs?: AppTab[];
  /** 표시할 탭 (기본: 전체). 발표회 범위 밖 탭은 숨김 */
  visibleTabs?: AppTab[];
  onTabChange?: (tab: AppTab) => void;
  footer?: ReactNode;
  className?: string;
};

const tabs: { id: AppTab; label: string; icon: IconName }[] = [
  { id: 'room', label: '우리 방', icon: 'room' },
  { id: 'match', label: '매칭', icon: 'match' },
  { id: 'persona', label: '페르소나', icon: 'persona' },
  { id: 'community', label: '커뮤니티', icon: 'community' },
  { id: 'plans', label: '이용권', icon: 'plans' },
  { id: 'all', label: '전체', icon: 'all' },
];

export function AppShell({ children, title, subtitle, showBack = false, onBack, activeTab, enabledTabs, visibleTabs, onTabChange, footer, className = '' }: AppShellProps) {
  const shownTabs = visibleTabs ? tabs.filter((tab) => visibleTabs.includes(tab.id)) : tabs;
  return (
    <div className={`app-shell ${activeTab ? 'has-nav' : ''} ${className}`}>
      {(title || showBack) && (
        <header className="app-header">
          {showBack ? (
            <button className="icon-button app-header-back" type="button" onClick={onBack} aria-label="뒤로 가기">
              ‹
            </button>
          ) : null}
          <div className="app-header-copy">
            {title ? <h1>{title}</h1> : null}
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
        </header>
      )}
      <main className="app-content">{children}</main>
      {footer ? <div className="app-footer">{footer}</div> : null}
      {activeTab ? (
        <nav className="bottom-nav" aria-label="주 메뉴" style={{ gridTemplateColumns: `repeat(${shownTabs.length}, 1fr)` }}>
          <div className="side-brand" aria-hidden="true"><span><Icon name="bed" size={24} /></span><div><strong>룸메궁합</strong><small>AI 가상 동거 룸메이트 매칭</small></div></div>
          {shownTabs.map((tab) => {
            const enabled = enabledTabs?.includes(tab.id) ?? activeTab === tab.id;
            return (
            <button
              key={tab.id}
              type="button"
              className={`bottom-nav-item ${activeTab === tab.id ? 'is-active' : ''}`}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              aria-label={`${tab.label}${!enabled ? ', 준비 중' : ''}`}
              disabled={!enabled}
              onClick={() => onTabChange?.(tab.id)}
            >
              <span className="bottom-nav-icon" aria-hidden="true"><Icon name={tab.icon} size={22} strokeWidth={1.9} /></span>
              <span>{tab.label}</span>
            </button>
          );})}
          <p className="side-foot">휴대폰에서도 같은 주소로 이용할 수 있어요.</p>
        </nav>
      ) : null}
    </div>
  );
}
