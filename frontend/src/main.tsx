import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';

/** 예기치 못한 화면 오류 시 빈 화면 대신 안내와 다시 시작 버튼 표시 */
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <div style={{ padding: '72px 28px', textAlign: 'center' }}>
      <h2>화면을 표시하지 못했어요</h2>
      <p style={{ color: '#5f6b77' }}>잠시 후 다시 시도해 주세요.</p>
      <button type="button" className="flow-button" onClick={() => { sessionStorage.clear(); window.location.reload(); }}>처음부터 다시 시작</button>
    </div>;
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
