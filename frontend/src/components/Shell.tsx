import type { ReactNode } from 'react';

export type AppTab = 'room' | 'match' | 'persona' | 'all';

type AppShellProps = {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  showBack?: boolean;
  onBack?: () => void;
  activeTab?: AppTab;
  enabledTabs?: AppTab[];
  onTabChange?: (tab: AppTab) => void;
  footer?: ReactNode;
  className?: string;
};

const tabs: { id: AppTab; label: string; icon: string }[] = [
  { id: 'room', label: '우리 방', icon: '⌂' },
  { id: 'match', label: '매칭', icon: '♧' },
  { id: 'persona', label: '페르소나', icon: '✧' },
  { id: 'all', label: '전체', icon: '☷' },
];

export function AppShell({ children, title, subtitle, showBack = false, onBack, activeTab, enabledTabs, onTabChange, footer, className = '' }: AppShellProps) {
  return (
    <div className={`app-shell ${className}`}>
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
        <nav className="bottom-nav" aria-label="주 메뉴">
          {tabs.map((tab) => {
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
              <span className="bottom-nav-icon" aria-hidden="true">{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );})}
        </nav>
      ) : null}
    </div>
  );
}
