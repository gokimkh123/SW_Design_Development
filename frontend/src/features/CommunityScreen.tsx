import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { CommunityBoard, CommunityPost, CommunityPostSummary, CommunityView, GrievanceCategory } from '../api/types';
import './community.css';

const BOARDS: Record<CommunityBoard, { label: string; lead: string; empty: string }> = {
  free: { label: '자유게시판', lead: '같은 생활관 학생들과 자유롭게 이야기해요', empty: '아직 글이 없어요. 첫 글을 남겨 보세요.' },
  grievance: { label: '애로사항 제안', lead: '불편한 점을 제안하면 공감 5개 이상인 글을 생활관에 전달해요', empty: '아직 제안이 없어요. 생활하며 불편한 점을 알려 주세요.' },
};
const CATEGORIES: GrievanceCategory[] = ['시설', '소음', '청결', '식당', '안전', '기타'];
const MAX_PHOTOS = 3;

function timeText(value: string): string {
  const diff = (Date.now() - new Date(value).getTime()) / 1000;
  if (diff < 60) return '방금';
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  const date = new Date(value);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function message(cause: unknown, fallback: string) { return cause instanceof Error ? cause.message : fallback; }

/** 사진을 긴 변 1280px · JPEG로 다시 그려 용량을 줄인다(위치 정보 등 EXIF도 함께 제거). 서버 한도 600KB 이내 */
async function shrinkPhoto(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  try {
    for (const [edge, quality] of [[1280, 0.8], [1024, 0.7], [800, 0.6]] as const) {
      const scale = Math.min(1, edge / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const url = canvas.toDataURL('image/jpeg', quality);
      if (url.length < 780_000) return url;
    }
  } finally { bitmap.close(); }
  throw new Error('사진이 너무 커요. 다른 사진을 골라 주세요.');
}

/** 기숙사 커뮤니티: 자유게시판 · 애로사항 제안. 글 · 댓글은 익명(글쓴이 · 익명N)으로 표시 */
export function CommunityScreen({ view, onViewChange }: { view: CommunityView; onViewChange: (view: CommunityView) => void }) {
  const [board, setBoard] = useState<CommunityBoard>('free');
  const [posts, setPosts] = useState<CommunityPostSummary[] | null>(null);
  const [error, setError] = useState('');
  const top = useRef<HTMLDivElement>(null);

  const load = useCallback(async (target: CommunityBoard) => {
    setPosts(null); setError('');
    try { const result = await api.listPosts(target); setPosts(result.posts); }
    catch (cause) { setError(message(cause, '글 목록을 불러오지 못했어요.')); setPosts([]); }
  }, []);

  useEffect(() => { if (view.kind === 'list') void load(board); }, [board, view.kind, load]);
  useEffect(() => { top.current?.scrollIntoView({ block: 'start' }); }, [view]);

  return <div className="flow-screen community-screen" ref={top}>
    {view.kind === 'list' && <>
      <div className="community-tabs" role="tablist" aria-label="게시판">
        {(Object.keys(BOARDS) as CommunityBoard[]).map(key => <button key={key} type="button" role="tab" aria-selected={board === key} className={board === key ? 'is-active' : ''} onClick={() => setBoard(key)}>{BOARDS[key].label}</button>)}
      </div>
      <div className="community-head"><p>{BOARDS[board].lead}</p><button className="flow-button community-write" type="button" onClick={() => onViewChange({ kind: 'write' })}>글쓰기</button></div>
      <p className="community-rule">모든 글과 댓글은 익명으로 표시돼요. 욕설 · 비하 · 연락처 · 링크는 올릴 수 없고, 신고가 3회 쌓이면 자동으로 숨겨져요.</p>
      {error && <p className="extra-error" role="alert">{error}</p>}
      {posts === null && <p className="flow-notice">글을 불러오는 중이에요…</p>}
      {posts && posts.length === 0 && !error && <p className="community-empty">{BOARDS[board].empty}</p>}
      {posts && posts.length > 0 && <ul className="community-list">{posts.map(post => <li key={post.post_id}>
        <button type="button" className="community-item" onClick={() => onViewChange({ kind: 'post', postId: post.post_id })}>
          <span className="community-item-tags">{post.category && <em>{post.category}</em>}{post.forwarded && <em className="is-forwarded">생활관 전달</em>}{post.is_mine && <em className="is-mine">내 글</em>}</span>
          <strong>{post.title}</strong>
          <span className="community-item-excerpt">{post.excerpt}</span>
          <span className="community-meta"><span>공감 {post.like_count}</span><span>댓글 {post.comment_count}</span>{post.image_count > 0 && <span>사진 {post.image_count}</span>}<span>{timeText(post.created_at)}</span></span>
        </button>
      </li>)}</ul>}
    </>}
    {view.kind === 'write' && <WriteView board={board} onDone={post => onViewChange({ kind: 'post', postId: post.post_id })} />}
    {view.kind === 'post' && <PostView postId={view.postId} onBack={() => onViewChange({ kind: 'list' })} />}
  </div>;
}

function WriteView({ board, onDone }: { board: CommunityBoard; onDone: (post: CommunityPost) => void }) {
  const [category, setCategory] = useState<GrievanceCategory>('시설');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [photos, setPhotos] = useState<{ name: string; url: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const ready = title.trim().length >= 2 && body.trim().length >= 2;

  async function pick(files: FileList | null) {
    if (!files?.length) return;
    setError('');
    const room = MAX_PHOTOS - photos.length;
    const chosen = [...files].filter(file => file.type.startsWith('image/')).slice(0, room);
    if (files.length > room) setError(`사진은 최대 ${MAX_PHOTOS}장까지 올릴 수 있어요.`);
    try {
      const shrunk = await Promise.all(chosen.map(async file => ({ name: file.name, url: await shrinkPhoto(file) })));
      setPhotos(current => [...current, ...shrunk].slice(0, MAX_PHOTOS));
    } catch (cause) { setError(message(cause, '사진을 불러오지 못했어요.')); }
    if (fileInput.current) fileInput.current.value = '';
  }

  async function submit() {
    if (!ready || busy) return;
    setBusy(true); setError('');
    try {
      let post = await api.createPost({ board, title: title.trim(), body: body.trim(), ...(board === 'grievance' ? { category } : {}) });
      for (const photo of photos) {
        try { post = await api.uploadPostImage(post.post_id, photo.url); }
        catch { /* 글은 이미 올라갔으므로 사진 실패는 상세 화면에서 개수로 확인 */ }
      }
      onDone(post);
    } catch (cause) { setError(message(cause, '글을 올리지 못했어요.')); setBusy(false); }
  }

  return <section className="flow-card community-form">
    <h2>{BOARDS[board].label}</h2>
    {board === 'grievance' && <div className="community-categories" role="radiogroup" aria-label="분류">{CATEGORIES.map(item => <button key={item} type="button" role="radio" aria-checked={category === item} className={category === item ? 'is-active' : ''} onClick={() => setCategory(item)}>{item}</button>)}</div>}
    <label>제목<input value={title} maxLength={40} onChange={event => setTitle(event.target.value)} placeholder={board === 'grievance' ? '예) 3층 세탁실 건조기 고장' : '제목을 입력하세요'} /></label>
    <label>내용<textarea value={body} maxLength={1000} rows={7} onChange={event => setBody(event.target.value)} placeholder={board === 'grievance' ? '어디서 · 언제 · 어떤 불편이 있는지 적어 주세요.' : '내용을 입력하세요'} /></label>
    <small className="community-count">{body.length} / 1000</small>
    <div className="community-photos">
      <span className="community-photos-label">사진 첨부 <small>{photos.length} / {MAX_PHOTOS}</small></span>
      <div className="community-photo-row">
        {photos.map((photo, index) => <div className="community-photo-thumb" key={`${photo.name}-${index}`}>
          <img src={photo.url} alt={`첨부 사진 ${index + 1}`} />
          <button type="button" aria-label={`사진 ${index + 1} 삭제`} onClick={() => setPhotos(current => current.filter((_, i) => i !== index))}>×</button>
        </div>)}
        {photos.length < MAX_PHOTOS && <button type="button" className="community-photo-add" onClick={() => fileInput.current?.click()} disabled={busy}><span aria-hidden="true">＋</span>사진 추가</button>}
      </div>
      <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={event => void pick(event.target.files)} />
      <small className="community-photo-note">{board === 'grievance' ? '고장 · 파손 부위처럼 상황을 보여 주는 사진을 올려 주세요. ' : ''}다른 사람의 얼굴이나 개인 정보가 보이지 않게 해 주세요.</small>
    </div>
    {error && <p className="extra-error" role="alert">{error}</p>}
    <button className="flow-button" type="button" disabled={!ready || busy} onClick={() => void submit()}>{busy ? '올리는 중…' : '익명으로 올리기'}</button>
  </section>;
}

function PostView({ postId, onBack }: { postId: string; onBack: () => void }) {
  const [post, setPost] = useState<CommunityPost | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let active = true;
    void api.getPost(postId).then(value => { if (active) setPost(value); }).catch(cause => { if (active) setError(message(cause, '글을 불러오지 못했어요.')); });
    return () => { active = false; };
  }, [postId]);

  async function act(task: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try { await task(); } catch (cause) { setError(message(cause, '처리하지 못했어요.')); } finally { setBusy(false); }
  }

  if (!post) return <section className="flow-card community-post">{error ? <p className="extra-error" role="alert">{error}</p> : <p className="flow-notice">불러오는 중이에요…</p>}</section>;

  return <>
    <section className="flow-card community-post">
      <span className="community-item-tags">{post.category && <em>{post.category}</em>}{post.forwarded && <em className="is-forwarded">생활관 전달</em>}</span>
      <h2>{post.title}</h2>
      <span className="community-meta"><span>{post.is_mine ? '내 글' : '익명'}</span><span>{timeText(post.created_at)}</span></span>
      <p className="community-body">{post.body}</p>
      {post.images.length > 0 && <div className="community-post-photos">{post.images.map((src, index) => <a key={src} href={src} target="_blank" rel="noreferrer"><img src={src} alt={`첨부 사진 ${index + 1}`} loading="lazy" /></a>)}</div>}
      <div className="community-actions">
        <button type="button" className={`community-like${post.liked ? ' is-on' : ''}`} disabled={busy || post.is_mine || post.liked} onClick={() => void act(async () => { const result = await api.likePost(post.post_id); setPost({ ...post, liked: result.liked, like_count: result.like_count, forwarded: post.board === 'grievance' && result.like_count >= 5 }); })}>공감 {post.like_count}</button>
        {post.is_mine
          ? <button type="button" className="extra-inline-link" disabled={busy} onClick={() => void act(async () => { if (!window.confirm('이 글을 삭제할까요?')) return; await api.deletePost(post.post_id); onBack(); })}>삭제</button>
          : <button type="button" className="extra-inline-link" disabled={busy || post.reported} onClick={() => void act(async () => { if (!window.confirm('이 글을 신고할까요? 신고가 3회 쌓이면 숨겨져요.')) return; const result = await api.reportPost(post.post_id); if (result.hidden) { onBack(); return; } setPost({ ...post, reported: true }); setNotice('신고가 접수되었어요.'); })}>{post.reported ? '신고함' : '신고'}</button>}
      </div>
      {notice && <p className="community-notice" role="status">{notice}</p>}
      {error && <p className="extra-error" role="alert">{error}</p>}
    </section>
    <section className="flow-card community-comments" aria-label="댓글">
      <h3>댓글 {post.comments.length}</h3>
      {post.comments.length === 0 && <p className="community-empty">첫 댓글을 남겨 보세요.</p>}
      <ul>{post.comments.map(item => <li key={item.comment_id}>
        <div><b className={item.author === '글쓴이' ? 'is-writer' : ''}>{item.author}</b><span>{timeText(item.created_at)}</span>
          {item.is_mine
            ? <button type="button" className="extra-inline-link" disabled={busy} onClick={() => void act(async () => setPost(await api.deleteComment(item.comment_id)))}>삭제</button>
            : <button type="button" className="extra-inline-link" disabled={busy} onClick={() => void act(async () => { if (!window.confirm('이 댓글을 신고할까요?')) return; const result = await api.reportComment(item.comment_id); setNotice(result.hidden ? '신고가 쌓여 댓글이 숨겨졌어요.' : '신고가 접수되었어요.'); if (result.hidden) setPost(await api.getPost(post.post_id)); })}>신고</button>}
        </div>
        <p>{item.body}</p>
      </li>)}</ul>
      <form className="community-comment-form" onSubmit={event => { event.preventDefault(); const text = comment.trim(); if (!text) return; void act(async () => { setPost(await api.addComment(post.post_id, text)); setComment(''); }); }}>
        <input value={comment} maxLength={300} onChange={event => setComment(event.target.value)} placeholder="익명으로 댓글 달기" aria-label="댓글 입력" />
        <button className="flow-button" type="submit" disabled={busy || !comment.trim()}>등록</button>
      </form>
    </section>
  </>;
}
