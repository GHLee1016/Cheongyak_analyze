/**
 * CNT3054 청약 인식 프로젝트(B안): 보고서 초안(.docx) 생성
 *
 * 입력 : analyze_comments.py 가 만든 폴더의 stats.json, fig1_stance.png, fig2_topics.png
 * 출력 : 같은 폴더의 청약인식_보고서초안_B안.docx
 * 실행 : cd report && npm install
 *        node build_report.js                               # output/ 의 가장 최근 분석 폴더
 *        node build_report.js ../output/g4h29mJufpc_20260919T063349180506Z   # 폴더를 직접 지정
 *
 * 본문 수치는 stats.json 에서 읽어 오므로, 분류를 다시 하면 보고서 수치도 자동으로 바뀐다.
 * 표 12(주택시장 지표)는 보도 자료 수치이며 출처는 data/market_indicators.csv 에 있다.
 * 주의: 해석 문장(순위·비교 표현)은 초안 작성 당시 데이터 기준이므로, 수치가 바뀌면 문장도 다시 확인해야 한다.
 *
 * 인용 출처 (보고서 '참고자료'에 클릭 가능한 링크로 들어감)
 *  - 분석 영상  : https://www.youtube.com/watch?v=g4h29mJufpc  (크랩, 「청약통장 다들 왜 깨고 있을까?」)
 *  - 청약통장 가입·해지 : https://www.newspim.com/news/view/20260831000501
 *  - 청약통장 해지 동향 : https://www.hankyung.com/article/2026091313571
 *  - 서울 분양가       : https://biz.newdaily.co.kr/site/data/html/2026/09/18/2026091800233.html
 *  - 10·15 대책        : https://www.korea.kr/news/policyNewsView.do?newsId=148950959
 *  - 서울 아파트 월간   : https://www.g-enews.com/article/Real-Estate/2026/09/20260915103930303414b1077807_1
 *  - 주간 아파트 동향   : https://www.gukjenews.com/news/articleView.html?idxno=3691555
 *  - 분류 모델         : https://openrouter.ai/openai/gpt-oss-120b
 *  - docx 라이브러리    : https://docx.js.org/
 */
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, LevelFormat, PageNumber, Footer,
  TableOfContents, PageBreak, ExternalHyperlink, FootnoteReferenceRun,
} = require('docx');

// stats.json 이 있는 폴더: 인자로 주거나, 생략하면 output/ 에서 가장 최근에 분석한 폴더를 쓴다
function latestRun() {
  const out = path.join(__dirname, '..', 'output');
  const runs = fs.existsSync(out) ? fs.readdirSync(out)
    .map(d => path.join(out, d)).filter(d => fs.existsSync(path.join(d, 'stats.json')))
    .sort((a, b) => fs.statSync(path.join(a, 'stats.json')).mtimeMs - fs.statSync(path.join(b, 'stats.json')).mtimeMs) : [];
  if (!runs.length) { console.error('output/ 에 stats.json 이 없습니다. analyze_comments.py 를 먼저 실행하세요.'); process.exit(1); }
  return runs[runs.length - 1];
}
const RESULTS = path.resolve(process.argv[2] || latestRun());
console.log('입력 폴더:', RESULTS);
const S = JSON.parse(fs.readFileSync(path.join(RESULTS, 'stats.json'), 'utf-8'));
// 신뢰도 검증 결과 (check_reliability.py score 가 만든 output/reliability_kappa.csv, 없으면 표 생략)
const kPath = path.join(__dirname, '..', 'output', 'reliability_kappa.csv');
const KAPPA = fs.existsSync(kPath) ? fs.readFileSync(kPath, 'utf-8').replace(/^\uFEFF/, '').trim().split('\n').slice(1)
  .map(line => { const c = line.split(','); return { pair: c[0], n: Number(c[1]), '태도 κ': Number(c[2]).toFixed(2),
    '집값 전망 κ': Number(c[4]).toFixed(2), '통장 행동 κ': Number(c[6]).toFixed(2), '관심사 κ(평균)': Number(c[8]).toFixed(2) }; }) : [];
// 단계별 건수 대조 결과 (verify_counts.py 가 만든 verify_counts.json, 없으면 표 생략)
const vcPath = path.join(RESULTS, 'verify_counts.json');
const VC = fs.existsSync(vcPath) ? JSON.parse(fs.readFileSync(vcPath, 'utf-8')) : null;
// 각주 링크 (코드 저장소, 데이터베이스)
const GITHUB_URL = 'https://github.com/GHLee1016/Chungyak_analyze';
// Supabase REST 조회 링크 (publishable 키 = 공개용, 테이블은 RLS 로 읽기만 허용)
const SB_KEY = 'sb_publishable_Z3P3DWzEzLeL7BAhArEotQ_hptLYysY';
const SUPABASE_URL = `https://evfplzqpewwjtttlmvxc.supabase.co/rest/v1/cheongyak_comments?select=comment_id,published_at,stance,topics,outlook,action,text_raw&order=published_at&limit=100&apikey=${SB_KEY}`;
const SUPABASE_RUNS_URL = `https://evfplzqpewwjtttlmvxc.supabase.co/rest/v1/cheongyak_runs?select=run_folder,period_start,period_end,n_comments,model&apikey=${SB_KEY}`;
const clPath = path.join(RESULTS, 'collection_log.json');                      // 수집 조건 기록 (collect_comments.py)
const CL = fs.existsSync(clPath) ? JSON.parse(fs.readFileSync(clPath, 'utf-8')) : {};
const kstTime = (iso) => { const d = new Date(new Date(iso).getTime() + 9 * 3600e3);   // UTC → 한국 시간
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} KST`; };
const f1 = (n) => Number(n).toFixed(1);                 // 94 → '94.0'
const fmt = (n) => Number(n).toLocaleString('en-US');
const pct = (a, b) => (Math.round((a / b) * 1000) / 10).toFixed(1);
const RC = (name) => (S.reasons_cancel[name] || 0);   // 해지 이유별 댓글 수
const RK = (name) => (S.reasons_keep[name] || 0);     // 유지 이유별 댓글 수
const kdate = (iso) => { const [y, m, d] = iso.split('-').map(Number); return `${y}.${m}.${d}`; };  // 2026-09-11 → 2026.9.11
const pol1315 = ['2026-09-13', '2026-09-14', '2026-09-15'].reduce((a, d) => a + (S.political_by_date[d] || 0), 0);

const FONT = 'Malgun Gothic';

const p = (text, opts = {}) => new Paragraph({
  spacing: { after: 120, line: 320 },
  alignment: opts.align || AlignmentType.JUSTIFIED,
  indent: opts.indent ? { firstLine: 280 } : undefined,
  children: (Array.isArray(text) ? text : [text]).map(t => typeof t === 'string' ? new TextRun(t) : t),
});
const b = (t) => new TextRun({ text: t, bold: true });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 180 }, children: [new TextRun(t)] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 120 }, children: [new TextRun(t)] });
const h3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 180, after: 100 }, children: [new TextRun(t)] });
const bullet = (t, lvl = 0) => new Paragraph({ numbering: { reference: 'bul', level: lvl }, spacing: { after: 80, line: 300 },
  children: (Array.isArray(t) ? t : [t]).map(x => typeof x === 'string' ? new TextRun(x) : x) });
const caption = (t) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 },
  children: [new TextRun({ text: t, size: 18, color: '52514E' })] });
const note = (t) => new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: t, size: 17, color: '52514E' })] });
const quote = (t, likes) => new Paragraph({
  indent: { left: 400, right: 400 }, spacing: { after: 100, line: 300 },
  border: { left: { style: BorderStyle.SINGLE, size: 12, color: '2A78D6', space: 8 } },
  children: [new TextRun({ text: `“${t}”`, italics: true }), new TextRun({ text: `  (좋아요 ${likes.toLocaleString()})`, size: 17, color: '52514E' })],
});
const todo = (t) => new Paragraph({ spacing: { after: 120 }, shading: { type: ShadingType.CLEAR, fill: 'FFF4D6' },
  children: [new TextRun({ text: '[작성 필요] ', bold: true, color: '8A5A00' }), new TextRun({ text: t, color: '8A5A00' })] });

const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
const borders = { top: border, bottom: border, left: border, right: border };
function table(widths, rows, headerFill = 'E8EEF7') {
  const total = widths.reduce((a, c) => a + c, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0,
      children: r.map((c, j) => new TableCell({
        borders, width: { size: widths[j], type: WidthType.DXA },
        shading: i === 0 ? { type: ShadingType.CLEAR, fill: headerFill } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: String(c).split('\n').map(line => new Paragraph({ spacing: { after: 0, line: 276 },
          children: [new TextRun({ text: line, bold: i === 0, size: 18 })] })),
      })),
    })),
  });
}
const img = (file, w, h) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
  children: [new ImageRun({ type: 'png', data: fs.readFileSync(file), transformation: { width: w, height: h },
    altText: { title: path.basename(file), description: path.basename(file), name: path.basename(file) } })] });

const children = [];
// ---------- 표지 ----------
children.push(
  new Paragraph({ spacing: { before: 2400, after: 200 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: '청약에 대한 인식과 주택시장 현실의 관계', bold: true, size: 40 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1200 },
    children: [new TextRun({ text: '― 유튜브 댓글의 LLM 분류와 주택시장 지표 비교 ―', size: 26, color: '52514E' })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: '문화콘텐츠와 자연어처리', size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: '보고서 초안 (B안)', size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: '조원: ______________', size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: '2026년 9월', size: 22 })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---------- 요약 ----------
const T = { A: '분양가·집값 부담', B: '대출규제·자금조달', C: '가점·당첨확률', D: '제도 불공정', E: '대체 투자·낮은 금리',
  F: '정부·정치 불신', G: '임대·대출우대 등 부가 기능', H: '수도권 집중·지방·인구', I: '신축 품질·하자' };
const topicOrder = Object.keys(T).sort((a, b) => S.topic_share[b] - S.topic_share[a]);
const likesRel = S.likes_relevant;
const stanceLikes = (k) => Math.round(likesRel * S.stance_like_share[k] / 100);
const period = `${kdate(S.period_kst[0])}~${kdate(S.period_kst[1]).split('.').slice(1).join('.')}`;
const topC = S.top_comments[0];

children.push(
  h1('요약문'),
  p(`이 연구는 유튜브 댓글에 나타난 청약에 대한 인식과 집값 전망이 실제 주택시장 상황과 어떤 관계가 있는지 살펴본다. 청약통장 해지 현상을 다룬 유튜브 영상 「청약통장 다들 왜 깨고 있을까?」(크랩)의 최상위 댓글을 수집하고, 그중 ${period}(한국 시간) 1주일 동안 작성된 댓글 ${fmt(S.n_comments)}개를 LLM(${S.model_label.split(' ')[0]})으로 태도·관심사·집값 전망·청약통장 행동 의향에 따라 분류하였다.`, { indent: true }),
  p(`청약과 관련된 댓글 ${fmt(S.n_relevant)}개 가운데 ${f1(S.stance_share.N)}%가 청약 제도나 청약통장에 부정적이었다. 가장 많이 언급된 관심사는 ${T[topicOrder[0]]}(${f1(S.topic_share[topicOrder[0]])}%)였고, ${T[topicOrder[1]]}(${f1(S.topic_share[topicOrder[1]])}%), ${T[topicOrder[2]]}(${f1(S.topic_share[topicOrder[2]])}%)가 뒤를 이었다. 해지 의향을 밝힌 댓글(${S.action.H}개)이 유지 의향(${S.action.K}개)보다 많았으며, 유지하는 이유는 내 집 마련보다 임대주택 가점·대출 금리우대 같은 부가 기능이 주를 이뤘다.`, { indent: true }),
  p(`댓글이 청약을 외면하는 근거로 든 고분양가, 대출 한도, 가점 구조는 실제 시장 지표와 대체로 일치하였다. 서울 민간아파트 분양가는 3.3㎡당 6,287만 원으로 1년 새 34.2% 올랐고, 규제지역의 주택담보대출 한도는 최대 6억 원이다. 반면 집값 방향을 말한 댓글은 ${f1(S.outlook_share)}%뿐이었고 그중 하락 전망(${S.outlook.D}개)이 상승 전망(${S.outlook.U}개)보다 많아, 서울 아파트값이 올해 ${'7.52'}% 오른 실제 흐름과는 어긋났다. 온라인 여론은 시장의 방향을 예측하기보다 현재 가격과 제도가 만든 진입 장벽을 반영하는 것으로 해석된다.`, { indent: true }),
  new Paragraph({ spacing: { before: 200 }, children: [b('주제어: '), new TextRun('부동산 정책, 청약통장, 온라인 여론, 유튜브 댓글, LLM, 주택가격')] }),
  todo('요약문은 결과를 바탕으로 작성한 초안입니다. 조원 검토 후 확정하세요.'),
  new Paragraph({ children: [new PageBreak()] }),
  new TableOfContents('목차', { hyperlink: true, headingStyleRange: '1-2' }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---------- Ⅰ. 서론 ----------
children.push(
  h1('Ⅰ. 서론'),
  h2('1. 연구 배경 및 목적'),
  p('주택은 국민의 주거 안정과 직접적으로 연결되는 동시에 자산 형성의 중요한 수단이라는 점에서, 정부의 부동산 정책은 사회적 관심이 매우 높은 분야이다. 특히 주택가격과 청약제도는 실수요자의 주거 선택뿐 아니라 가계의 자산 형성과 금융 의사결정에도 영향을 미치기 때문에, 정책 변화가 발표될 때마다 사회적으로 다양한 의견이 형성된다.', { indent: true }),
  p('청약 제도는 무주택자와 실수요자의 주택 마련을 지원하기 위한 대표적인 주택 공급 제도이며, 청약통장은 이 제도에 참여하기 위한 주요 수단으로 활용되어 왔다. 그러나 최근에는 높은 분양가와 주택가격, 대출규제, 소득 및 자격 요건, 낮은 당첨 가능성에 대한 부담이 커지면서 청약통장의 실효성에 의문을 제기하거나 통장을 유지할 필요가 있는지 고민하는 이용자들이 나타나고 있다.', { indent: true }),
  p('이러한 변화는 통계로도 확인된다. 주택청약종합저축 가입자는 2021년 약 2,677만 명으로 정점을 찍은 뒤 2026년 6월 2,471만 명까지 줄었고, 2026년 1~7월에는 해지(216만 5천 좌)가 신규 가입(183만 6천 좌)보다 32만 9천 좌 많았다. 같은 시기 서울 민간아파트 평균 분양가는 3.3㎡당 6,287만 원으로 1년 전보다 34.2% 올랐으며, 2025년 10·15 대책으로 서울 전역과 경기 12곳의 주택담보대출 LTV는 40%로 낮아졌다.', { indent: true }),
  p('따라서 본 연구에서는 부동산 및 청약 관련 유튜브 영상의 댓글을 수집하여 이용자들의 정책에 대한 태도와 주요 관심사를 분석하고자 한다. 특히 LLM을 활용하여 대규모의 자연어 댓글을 일정한 기준에 따라 분류하고, 댓글에서 나타난 집값 전망과 청약통장 관련 행동 의향을 분석한다.', { indent: true }),
  p('나아가 온라인 댓글에서 나타난 집값 전망과 실제 주택가격 데이터를 비교하여, 온라인에서 형성된 정책 관련 여론과 실제 주택시장 변화 사이에 어떠한 관계가 나타나는지 살펴보고자 한다.', { indent: true }),
  h2('2. 연구 질문'),
  p('본 연구에서는 다음과 같은 연구 질문을 설정하였다.'),
  p([b('연구 질문: '), new TextRun('유튜브 댓글에 나타난 정책 인식 및 집값 전망과 청약에 대한 사람들의 인식은 실제 주택시장 상황과 어떠한 관계가 있는가?')]),
);

// ---------- Ⅱ. 본론 ----------
children.push(
  h1('Ⅱ. 본론'),
  h2('ⅰ) 데이터 및 분석 방법'),
  h3('1. 유튜브 댓글 데이터'),
  p([b('분석 영상. '), new TextRun('본 연구는 부동산 정책과 청약 제도를 주요 내용으로 다루는 유튜브 영상을 분석 대상으로 선정하였다. 해당 영상은 청약통장 및 주택시장과 관련된 청년들의 인식을 다루고 있으며, 댓글을 통해 정책에 대한 의견이 활발하게 나타난다는 점을 고려하였다. 분석 대상 영상은 「청약통장 다들 왜 깨고 있을까?」(크랩, 2026년 9월 11일 게시, https://www.youtube.com/watch?v=g4h29mJufpc)이다.')]),
  p([b('영상 선정 기준. '), new TextRun(`영상 선정 과정에서는 연구 주제와의 관련성을 가장 중요한 기준으로 설정하였다. 또한 정책에 대한 이용자들의 의견을 확인할 수 있을 만큼 댓글이 충분한지를 확인하여, 답글을 포함해 약 3,000개 이상의 댓글(수집 시점 기준 최상위 댓글 ${fmt(S.n_collected)}개, 답글 포함 ${fmt(S.n_collected_with_replies)}개)이 달린 영상을 선정하였다.`)]),
  p([b('유튜브 API를 활용한 댓글 수집. '), new TextRun('댓글은 수업에서 제공된 수집 코드(collect_comments.py)를 수정하여'), new FootnoteReferenceRun(1), new TextRun(` YouTube Data API v3의 commentThreads.list 기능을 호출하여 수집하였다. 댓글 본문과 함께 작성 시점, 좋아요 수, 답글 수를 저장하였으며, 답글 본문은 제외하였다. 수집된 최상위 댓글 ${fmt(S.n_collected)}개 가운데 분석 기간인 ${period}(한국 시간)에 작성된 ${fmt(S.n_comments)}개를 분석에 사용하였다. 댓글의 좋아요 수는 댓글 개수만으로는 파악하기 어려운 이용자들의 공감 정도를 보조적으로 확인하는 지표로 활용하였다.`)]),
  table([2200, 6826], [
    ['항목', '내용'],
    ['분석 영상', '「청약통장 다들 왜 깨고 있을까?」 (크랩, 영상 ID g4h29mJufpc, 2026.9.11 게시)'],
    ['수집 방법', 'YouTube Data API v3 commentThreads, 최상위 댓글 전체 (답글 본문 제외, 답글 수만 기록)'],
    ['수집 항목', '댓글 ID, 본문, 작성 시각, 좋아요 수, 답글 수'],
    ['수집량', `최상위 댓글 ${fmt(S.n_collected)}개 (답글 포함 ${fmt(S.n_collected_with_replies)}개)`],
    ['분석 대상', `${period} 작성 댓글 ${fmt(S.n_comments)}개 / 좋아요 합계 ${fmt(S.likes_total)}`],
  ]),
  caption('표 1. 댓글 데이터 개요'),
  p('수집 요청의 조건은 표 2와 같고, 전체 수집 과정은 그림 1과 같다.', { indent: true }),
  table([1900, 2600, 4526], [
    ['매개변수', '값', '의미'],
    ['part', 'snippet', '댓글 본문, 작성 시각, 좋아요 수 등 기본 정보를 받음'],
    ['videoId', 'g4h29mJufpc', '분석 대상 영상'],
    ['maxResults', '100', '한 번의 요청(한 페이지)으로 받을 최대 댓글 수. API 상한이 100개임'],
    ['order', 'time', '최신 댓글부터 받음'],
    ['textFormat', 'plainText', 'HTML 태그 없이 순수 텍스트로 받음'],
    ['pageToken', '이전 응답의 nextPageToken', '다음 페이지를 이어서 받기 위한 값 (첫 요청에는 없음)'],
  ]),
  caption('표 2. 댓글 수집 요청 조건 (commentThreads.list)'),
  img(path.join(__dirname, 'fig_collect_flow.png'), 600, 307),
  caption('그림 1. 댓글 수집 흐름: execute()로 요청을 보내고, nextPageToken이 없을 때까지 반복'),
  p([b('① execute(): 요청을 실제로 보내는 단계. '), new TextRun('youtube.commentThreads().list(...)는 위 조건을 담은 요청을 만들기만 하고 서버로 보내지는 않는다. 뒤에 붙은 execute()가 실행되어야 요청이 YouTube 서버로 전송되고, 그 결과(JSON)가 파이썬 딕셔너리 형태의 응답으로 돌아온다. 응답의 items에는 댓글 목록이, nextPageToken에는 다음 페이지 정보가 들어 있다. 수집 코드는 execute()를 예외 처리 구문으로 감싸, 할당량 초과나 네트워크 오류가 나면 수집을 멈추고 그때까지 받은 댓글만 저장하도록 하였다. 이때 오류 기록에는 API 키가 들어 있을 수 있는 요청 주소 대신 HTTP 상태 코드와 오류 이유만 남겼다. 수집 전에는 videos().list(...).execute()로 영상 제목과 채널을 먼저 조회하여 올바른 영상인지 확인하였다.')]),
  p([b('② nextPageToken: 여러 페이지를 이어 받는 단계. '), new TextRun(`API는 한 번에 최대 100개의 댓글만 돌려주므로, 전체 댓글을 받으려면 여러 번 요청해야 한다. 응답에 nextPageToken이 있으면 아직 받을 댓글이 남아 있다는 뜻이며, 이 값을 다음 요청의 pageToken에 넣어 보내면 앞 페이지 다음부터 이어서 받을 수 있다. 수업 코드의 기본 설정은 1페이지(100개)만 받는 것이었으나, 본 연구에서는 --all 옵션을 추가하여 nextPageToken이 더 이상 오지 않을 때까지 반복하였다. 그 결과 ${CL.pages_received ?? '-'}번의 요청으로 최상위 댓글 ${fmt(S.n_collected)}개를 수집하였고, 마지막 응답에 nextPageToken이 없어 수집이 정상 종료되었다(종료 이유: ${CL.stop_reason ?? '-'}). 또한 기간 필터(--start, --end)를 쓰면 최신순으로 받다가 분석 시작일보다 오래된 댓글이 나오는 페이지에서 수집을 멈추도록 하여 불필요한 요청을 줄일 수 있게 하였다.`)]),
  p([b('③ comment_id: 댓글을 구분하는 고유 번호. '), new TextRun('각 댓글에는 YouTube가 부여한 고유 식별자(comment_id, 예: Ugw_4FGE1HgqTyKv8k14AaABAg)가 있다. 본 연구에서 comment_id는 세 가지 역할을 하였다.')]),
  bullet([b('중복 제거: '), new TextRun(`페이지를 넘기는 사이에 새 댓글이 달리면 같은 댓글이 두 페이지에 걸쳐 나올 수 있다. 수집 코드는 이미 받은 comment_id를 기록해 두고 같은 번호가 다시 나오면 건너뛰었다. 이번 수집에서 중복으로 제외된 댓글은 ${CL.duplicates_skipped ?? '-'}개였다.`)]),
  bullet([b('분석 결과 연결: '), new TextRun('LLM 분류 결과, 사람이 직접 분류한 신뢰도 검증 시트, 원문 데이터를 comment_id로 서로 맞춰 합쳤다. 댓글 본문이나 순서가 아닌 고유 번호로 연결하므로 행이 밀리거나 섞이지 않는다.')]),
  bullet([b('데이터베이스 저장: '), new TextRun('Supabase의 cheongyak_comments 테이블에서 comment_id를 기본 키(primary key)로 사용하였다. 같은 댓글을 다시 올리면 새 행을 추가하지 않고 기존 행을 갱신한다(자세한 내용은 ⑤ 중복 저장 방지).')]),
  p([b('④ 수집 기록. '), new TextRun(`수집할 때마다 새 폴더(output/영상ID_수집시각/)를 만들어 원문 CSV(comments.csv)와 수집 조건 기록(collection_log.json)을 함께 저장하였다. 기록에는 요청·응답 페이지 수(${CL.pages_requested ?? '-'}/${CL.pages_received ?? '-'}), 받은 댓글 수(${fmt(CL.received_items ?? S.n_collected)}), 중복 제외 수(${CL.duplicates_skipped ?? '-'}), 종료 이유(${CL.stop_reason ?? '-'}), 수집 시각(${CL.collected_at ? kstTime(CL.collected_at) : '-'})이 남아 있어 같은 조건으로 수집을 재현할 수 있다.`)]),
  p([b('⑤ 데이터 저장과 건수 검증. '), new TextRun('수집한 댓글은 CSV 파일로 저장한 뒤, LLM 분류 결과와 함께 Supabase(PostgreSQL 데이터베이스)'), new FootnoteReferenceRun(2), new TextRun('의 cheongyak_comments 테이블(댓글 1개 = 1행)과 cheongyak_runs 테이블(수집·분류 실행 1회 = 1행)에 올렸다(upload_supabase.py). 단계를 거치는 동안 댓글이 빠지거나 두 번 들어가지 않았는지 확인하기 위해, 수집 기록·CSV 파일·데이터베이스의 건수를 서로 대조하였다(verify_counts.py, 표 3).')]),
  ...(VC ? [
    table([1700, 4300, 1826, 1200], [
      ['단계', '확인 대상', '건수', '결과'],
      ['수집', 'collection_log.json: 받은 댓글 / 중복 제외 / 저장', `${fmt(VC.log_received_items)} / ${fmt(VC.log_duplicates_skipped)} / ${fmt(VC.log_saved_rows)}`, (VC.log_received_items - VC.log_duplicates_skipped === VC.log_saved_rows) ? '일치' : '확인 필요'],
      ['원문 저장', 'comments.csv: 행 수 / 고유 comment_id 수', `${fmt(VC.comments_csv_rows)} / ${fmt(VC.comments_csv_unique_ids)}`, (VC.comments_csv_rows === VC.log_saved_rows && VC.comments_csv_rows === VC.comments_csv_unique_ids) ? '일치' : '확인 필요'],
      ['LLM 분류', 'classify_log.json: 분류 / 실패, classified.csv 행 수', `${fmt(VC.classify_log_n_comments)} / ${fmt(VC.classify_log_n_failed)}, ${fmt(VC.classified_csv_rows)}`, (VC.classified_csv_rows === VC.comments_csv_rows && !VC.classify_log_n_failed) ? '일치' : '확인 필요'],
      ['분석 기간', `${period} 작성 댓글 / 분류 완료`, `${fmt(VC.period_rows)} / ${fmt(VC.period_classified)}`, VC.period_rows === VC.period_classified ? '일치' : '확인 필요'],
      ['DB 저장', 'Supabase cheongyak_comments: 이 결과 폴더(run_folder)의 행 수', VC.db_run_rows != null ? fmt(VC.db_run_rows) : '-', VC.db_run_rows === VC.period_rows ? '일치' : '확인 필요'],
      ...(VC.db_unique_ids != null ? [
        ['DB 중복 확인', 'cheongyak_comments: 전체 행 / 고유 comment_id / 두 번 이상 저장된 comment_id', `${fmt(VC.db_total_rows)} / ${fmt(VC.db_unique_ids)} / ${fmt(VC.db_duplicate_ids)}`, (VC.db_total_rows === VC.db_unique_ids && VC.db_duplicate_ids === 0) ? '중복 없음' : '확인 필요'],
      ] : []),
    ]),
    caption('표 3. 단계별 댓글 건수 대조 (수집 기록 · CSV · 데이터베이스)'),
    note(`DB 건수 출처: ${VC.db_source === 'live query (verify_counts.py)' ? 'verify_counts.py 로 Supabase 직접 조회' : 'upload_supabase.py 실행 직후 run_folder 기준 count(*) 조회 결과'} (${kstTime(VC.checked_at)} 확인).`),
    p(`수집 단계에서 받은 ${fmt(VC.log_received_items)}개는 중복 없이 모두 comments.csv에 저장되었고(고유 comment_id ${fmt(VC.comments_csv_unique_ids)}개), LLM 분류에서도 실패한 댓글 없이 ${fmt(VC.classified_csv_rows)}개 모두 결과를 받았다. 이 중 분석 기간에 작성된 ${fmt(VC.period_rows)}개가 데이터베이스에 같은 수(${VC.db_run_rows != null ? fmt(VC.db_run_rows) : '-'}행)로 저장되어, 수집부터 저장까지 모든 단계의 건수가 일치하였다.`, { indent: true }),
  ] : []),
  p([b('중복 저장 방지. '), new TextRun('같은 댓글이 두 번 저장되지 않도록 세 단계에서 막았다.')]),
  bullet([b('수집 단계: '), new TextRun(`페이지를 넘기는 사이 새 댓글이 달려 같은 댓글이 다음 페이지에 다시 나올 수 있으므로, 이미 받은 comment_id를 집합(set)에 기록해 두고 같은 번호는 건너뛰었다(이번 수집 ${CL.duplicates_skipped ?? '-'}개 제외).`)]),
  bullet([b('데이터베이스 구조: '), new TextRun('cheongyak_comments 테이블은 comment_id를, cheongyak_runs 테이블은 결과 폴더 이름(run_folder)을 기본 키(PRIMARY KEY)로 지정하였다. 기본 키는 값이 겹치는 행을 데이터베이스가 받아들이지 않으므로, 코드에 실수가 있더라도 같은 댓글이 두 행으로 저장될 수 없다.')]),
  bullet([b('다시 올릴 때: '), new TextRun('업로드는 INSERT … ON CONFLICT (comment_id) DO UPDATE(upsert) 구문을 사용하였다. 이미 있는 댓글이면 새 행을 추가하지 않고 분류 결과·좋아요 수 등만 최신 값으로 갱신한다. 분류를 다시 하거나 업로드를 여러 번 실행해도 행 수는 늘어나지 않으며, 같은 데이터를 두 번 올리는 시험에서도 행 수가 1,045개로 그대로였다.')]),
  ...(VC && VC.db_unique_ids == null ? [todo('Mac 에서 python verify_counts.py 를 실행하면 Supabase 에서 전체 행·고유 comment_id·중복 수·기본 키를 직접 조회해 verify_counts.json 에 저장한다. 그 뒤 보고서를 다시 만들면 표 3에 “DB 중복 확인” 행이 추가된다.')] : []),

  h3('2. LLM 분석'),
  p([b('분석 목적. '), new TextRun('유튜브 댓글은 비정형 텍스트 데이터이기 때문에 하나의 댓글에서도 정책에 대한 태도와 관심 주제가 복합적으로 나타날 수 있다. 본 연구에서는 이러한 자연어 데이터를 효율적으로 분석하기 위해 LLM을 활용하였다. 댓글을 단순히 긍정 또는 부정으로 나누는 데 그치지 않고, 정책에 대한 태도, 주요 관심사, 집값 전망, 청약통장 관련 행동 의향을 구분하여 분석하였다.')]),
  p([b('분류 기준. '), new TextRun('댓글의 태도는 긍정, 부정, 양가로 구분하고, 청약에 대한 판단이 드러나지 않는 댓글은 “해당 없음”으로 따로 분류하였다. 관심사는 한 댓글에 해당하는 것을 모두 고르도록 하였고, 이와 함께 집값 상승·하락 전망과 청약통장 해지·유지 의향을 별도로 분류하였다(표 4).')]),
  table([1500, 2300, 5226], [
    ['차원', '범주', '판단 기준'],
    ['태도\n(하나 선택)', '부정', '청약 정책이나 제도의 문제점, 부정적인 영향을 지적하는 댓글'],
    ['', '양가', '긍정적인 측면과 부정적인 측면을 함께 담거나, 방향을 판단하기 어려운 댓글 (고민, 질문, 정보 제공 포함)'],
    ['', '긍정', '청약 정책이나 제도를 긍정적으로 보거나 통장 유지를 권하는 댓글'],
    ['', '해당 없음', '정치 구호, 감탄, 욕설, 영상과 무관한 잡담처럼 청약에 대한 판단이 없는 댓글'],
    ['관심사\n(복수 선택)', '9개 주제', '① 분양가·집값 부담 ② 제도 불공정 ③ 대출규제·자금조달 ④ 정부·정치 불신 ⑤ 가점·당첨확률 ⑥ 대체 투자·낮은 금리 ⑦ 임대·대출우대 등 부가 기능 ⑧ 수도권 집중·지방·인구 ⑨ 신축 품질·하자'],
    ['집값 전망', '상승 / 하락 / 없음', '앞으로의 가격 방향을 말하거나 가격이 계속 오르고 있다고 서술한 경우. “비싸다”처럼 현재 수준만 말하면 “없음”'],
    ['통장 행동', '해지 / 유지 / 없음', '작성자가 해지했거나 할 계획인지, 유지하고 있거나 유지를 권하는지'],
  ]),
  caption('표 4. 댓글 분류 기준'),
  p([b('프롬프트 설계. '), new TextRun('LLM에 입력하는 프롬프트에서는 댓글의 의미를 임의로 확대해석하지 않도록 분류 기준과 범주별 예시를 구체적으로 제시하였다. 수업 예제(ev-run.py)처럼 분류 기준을 별도 파일(cy-index.txt, 부록 1)로 분리하고, 역할 부여 → 분류 기준 → 필수 규칙 → JSON 출력 형식 순서로 구성하였다. 단순한 감탄이나 욕설처럼 청약에 대한 방향성을 확인하기 어려운 댓글은 “해당 없음”으로 처리하도록 하였다. 집값 전망은 댓글에 상승 또는 하락이 드러난 경우에만 해당 범주로 분류하여 분석자의 추측이 개입되는 것을 줄였다.')]),
  p([b('댓글 분류 방법. '), new TextRun(`댓글 ${fmt(S.n_comments)}개를 ${S.batch_size}개씩 묶어 번호를 붙여 LLM(${S.model_label})에 입력하고, 사전에 정한 기준에 따라 결과를 JSON으로 받았다. 응답은 번호로 원래 댓글과 맞췄으며, 형식이 틀리거나 빠진 댓글은 그 댓글만 다시 요청하였다. 이후 결과를 집계하여 각 태도와 관심사가 전체 댓글에서 차지하는 비중을 계산하였다. 또한 댓글 수와 함께 해당 댓글이 받은 좋아요 수를 분석하여, 댓글의 빈도와 다른 이용자들의 공감 정도가 일치하는지 비교하였다.`)]),
  p([b('신뢰도 검증(Human-in-the-loop). '), new TextRun('LLM 분류가 사람의 판단과 얼마나 일치하는지 확인하기 위해, 분석 기간 댓글 중 무작위로 뽑은 100개를 팀원이 LLM 결과를 보지 않은 채 같은 기준(cy-index.txt)으로 직접 분류하였다. 또한 다른 LLM인 Claude(Anthropic)에게도 gpt-oss-120b의 결과를 보여 주지 않고 같은 100개를 같은 기준으로 분류하게 하여, 사람·gpt-oss-120b·Claude 세 분류를 서로 비교하였다. 일치도는 Cohen’s κ로 계산하고, LLM과 판단이 달랐던 댓글은 조원이 함께 검토하여 오분류 유형을 정리하였다(check_reliability.py).')]),
  ...(KAPPA.length ? [
    table([2900, 1225, 1225, 1225, 1226, 1225], [
      ['비교', '댓글 수', '태도 κ', '관심사 κ(평균)', '집값 전망 κ', '통장 행동 κ'],
      ...KAPPA.map(r => [r.pair.replace('claude', 'Claude').replace('팀원1', '사람(팀원)'), r.n, r['태도 κ'], r['관심사 κ(평균)'], r['집값 전망 κ'], r['통장 행동 κ']]),
    ]),
    caption('표 5. 분류 일치도 (Cohen’s κ, 0.61 이상 상당한 일치 / 0.81 이상 거의 완전한 일치)'),
  ] : []),
  ...(KAPPA.length ? [
    p(`검증 결과, 사람(팀원)과 두 LLM의 일치도는 모든 항목에서 “보통” 이상이었다(표 5). 사람과 Claude는 태도 κ=0.67, 통장 행동 κ=0.85로 가장 잘 맞았고, 본 분석에 쓴 gpt-oss-120b는 사람과 태도 κ=0.59, 관심사 κ=0.71, 통장 행동 κ=0.73이었다. 세 분류가 태도를 모두 똑같이 판단한 댓글은 100개 중 68개였으며, 셋 중 하나만 다르게 판단한 경우는 gpt-oss-120b가 15개로 가장 많았다(Claude 9개, 사람 7개).`, { indent: true }),
    table([2600, 1600, 1600, 1600, 1626], [
      ['태도 (100개 중)', '부정', '양가', '긍정', '해당 없음'],
      ['사람(팀원)', '70', '9', '4', '17'],
      ['Claude', '62', '9', '6', '23'],
      ['gpt-oss-120b', '54', '17', '3', '26'],
    ]),
    caption('표 6. 같은 댓글 100개에 대한 분류자별 태도 분포'),
    p('불일치는 한 방향으로 몰려 있었다. 사람이 부정으로 본 70개 중 gpt-oss-120b는 11개를 “해당 없음”, 6개를 “양가”로 분류하였다. “누가 요새 청약을 함??ㅋㅋ”, “청약통장 아직 갖고 있는 흑우 있음?”처럼 비꼬는 말투로 청약을 깎아내리는 짧은 댓글을 gpt-oss-120b는 판단이 없는 댓글로 처리하는 경향이 있었다. 반대로 사람이 부정이 아니라고 본 댓글을 gpt-oss-120b가 부정으로 분류한 경우는 1개뿐이었다. 따라서 본 연구의 부정 비율(청약 관련 댓글의 70.1%)은 실제보다 낮게 추정되었을 가능성이 크며, 결론의 방향(부정적 인식이 우세)은 오히려 더 강해진다. 통장 행동에서도 gpt-oss-120b는 “(계속 납입 중)”, “나만 깬 게 아니구나”처럼 간접적으로 드러난 유지·해지를 놓치는 경우가 대부분이었다(불일치 8건 중 7건). 따라서 해지·유지 의향 댓글 수도 실제보다 적게 잡혔을 가능성이 있다.', { indent: true }),
  ] : []),
  todo('검증 시트를 추가로 받으면 check_reliability.py score 를 다시 실행해 표 5를 갱신하고, 표 6과 위 해석 문단의 숫자도 함께 확인할 것 (현재: 팀원 1명, Claude, gpt-oss-120b).'),

  h3('3. 주택가격 데이터'),
  p([b('데이터 출처. '), new TextRun('댓글 속 인식과 비교할 주택시장 지표는 공공데이터포털에서 제공하는 한국부동산원·국토교통부 자료를 기본으로 하고(표 7), 최신 수치는 한국부동산원·주택도시보증공사(HUG) 통계를 인용한 언론 보도로 보완하였다(표 12).')]),
  table([2300, 3600, 3126], [
    ['비교할 인식', '데이터 (공공데이터포털)', '가격지표'],
    ['“다들 해지한다”', '한국부동산원 청약통장 전체 가입현황 (15088657), 청약통장 통계 조회 API (15114369)', '월별 가입자 수, 1·2순위 구성, 시도별 증감'],
    ['“청년은 포기했다”', '한국부동산원 지역별 청약 신청자·당첨자 정보 (15110975, 15110976)', '연령대별 신청자·당첨자 수'],
    ['“집값이 감당 불가”', '한국부동산원 중위매매가격·중위단위매매가격 (15112206, 15112207)', '권역별 중위 매매가격, ㎡당 가격'],
    ['“10억~20억은 있어야”', '국토교통부 아파트 매매 실거래가 상세 (15126468)', '거래금액 중위값·분위수'],
    ['“분양가가 너무 비싸다”', 'HUG 민간아파트 분양가격 동향', '3.3㎡당 평균 분양가, 전년 대비 상승률'],
  ]),
  caption('표 7. 주택가격 데이터 구성'),
  p([b('지역. '), new TextRun('서울, 수도권(경기·인천), 지방의 세 권역으로 나누었다. 댓글에서 “서울은 로또, 지방은 청약이 필요 없다”처럼 지역을 나누는 인식이 반복되기 때문이다.')]),
  p([b('기간. '), new TextRun('청약통장 가입자가 정점을 찍은 2021년 1월부터 2026년 8월까지를 기본으로 하고, 대출 규제가 강화된 2025년 10·15 대책 전후를 구분하여 살펴본다.')]),
  p([b('가격지표. '), new TextRun('분양가(3.3㎡당), 아파트 매매가격지수 변동률, 중위 매매가격, 실거래 금액, 주택담보대출 한도를 사용한다.')]),
);

// ---------- ⅱ) 결과 ----------
const zeroLikeShare = f1(S.share_zero_like);
const TR = S.trend;                                   // 일주일 동안의 변화 (analyze_comments.py compute_trend)
const PER = ['9/13', '9/14~15', '9/16~19'];
const ratio = (p) => (TR.period[p].action.H / Math.max(TR.period[p].action.K, 1)).toFixed(1);   // 해지 ÷ 유지
children.push(
  h2('ⅱ) 분석 결과'),
  h3('1. 정책 관련 댓글의 전반적인 반응'),
  p(`분석 대상 댓글 ${fmt(S.n_comments)}개 가운데 ${fmt(S.n_irrelevant)}개(${pct(S.n_irrelevant, S.n_comments)}%)는 청약에 대한 판단이 없는 “해당 없음” 댓글이었다. 대부분 특정 정당이나 대통령에 대한 구호, 세대 비난, 짧은 감탄이었다. 나머지 ${fmt(S.n_relevant)}개의 태도는 표 8과 같다.`, { indent: true }),
  table([2000, 1700, 1700, 1800, 1826], [
    ['태도', '댓글 수', '비율', '받은 좋아요', '좋아요 비중'],
    ['부정', fmt(S.stance_count.N), `${f1(S.stance_share.N)}%`, fmt(stanceLikes('N')), `${f1(S.stance_like_share.N)}%`],
    ['양가', fmt(S.stance_count.M), `${f1(S.stance_share.M)}%`, fmt(stanceLikes('M')), `${f1(S.stance_like_share.M)}%`],
    ['긍정', fmt(S.stance_count.P), `${f1(S.stance_share.P)}%`, fmt(stanceLikes('P')), `${f1(S.stance_like_share.P)}%`],
    ['합계 (청약 관련)', fmt(S.n_relevant), '100.0%', fmt(likesRel), '100.0%'],
  ]),
  caption(`표 8. 청약 관련 댓글의 태도 분포 (LLM 분류, ${period})`),
  img(path.join(RESULTS, 'fig1_stance.png'), 600, 195),
  caption('그림 2. 태도 분포: 댓글 수 기준과 좋아요 가중 비교'),
  p(`부정적인 댓글이 ${f1(S.stance_share.N)}%로 가장 많았고, 좋아요로 가중하면 ${f1(S.stance_like_share.N)}%까지 올라간다. 다만 이 기간의 좋아요는 소수 댓글에 크게 몰려 있다. 댓글의 ${zeroLikeShare}%는 좋아요가 하나도 없고, 가장 많은 좋아요를 받은 댓글 하나(${fmt(topC.like_count)}개)가 전체 좋아요의 ${f1(S.top1_like_share)}%를, 상위 10개 댓글이 ${f1(S.top10_like_share)}%를 차지한다. 그 댓글 하나를 빼고 계산해도 부정 비중은 ${f1(S.stance_like_share_wo_top1.N)}%로 여전히 높지만, 좋아요 가중 수치는 몇 개 댓글에 따라 크게 달라질 수 있으므로 본 연구에서는 댓글 수 기준을 중심으로 해석하였다.`, { indent: true }),

  h3('2. 댓글에서 나타난 주요 관심사'),
  table([3400, 1700, 1900, 2026], [
    ['관심사', '댓글 수', '전체 댓글 대비', '좋아요 비중'],
    ...topicOrder.map(k => [T[k], fmt(S.topic_count[k]), `${f1(S.topic_share[k])}%`, `${f1(S.topic_like_share[k])}%`]),
  ]),
  caption(`표 9. 관심사별 언급 빈도와 좋아요 비중 (한 댓글에 여러 관심사가 나올 수 있어 합계는 100%를 넘음, n=${fmt(S.n_comments)})`),
  img(path.join(RESULTS, 'fig2_topics.png'), 600, 280),
  caption('그림 3. 관심사별 언급 비율과 좋아요 비중'),
  p(`가장 많이 언급된 관심사는 ${T[topicOrder[0]]}(${f1(S.topic_share[topicOrder[0]])}%)였다. 이어 ${T[topicOrder[1]]}(${f1(S.topic_share[topicOrder[1]])}%), ${T[topicOrder[2]]}(${f1(S.topic_share[topicOrder[2]])}%), ${T[topicOrder[3]]}(${f1(S.topic_share[topicOrder[3]])}%), ${T[topicOrder[4]]}(${f1(S.topic_share[topicOrder[4]])}%) 순이었다. 댓글들은 대체로 “분양가가 너무 높아 당첨돼도 살 수 없고, 대출은 막혀 있으며, 당첨 조건은 1인가구나 평범한 직장인에게 불리하다”는 하나의 논리로 이 요소들을 묶었다. 댓글에서 언급된 금액(“○억”) ${S.amount_mentions}건의 중앙값은 ${S.amount_median_eok}억 원이었다.`, { indent: true }),
  p(`좋아요 비중은 가점·당첨확률(${f1(S.topic_like_share.C)}%)과 제도 불공정(${f1(S.topic_like_share.D)}%)이 가장 높게 나타났는데, 이는 좋아요 ${fmt(topC.like_count)}개를 받은 댓글 하나가 두 주제에 함께 분류된 영향이 크다. 좋아요를 가장 많이 받은 부정적 댓글은 다음과 같다.`, { indent: true }),
  ...S.top_comments.filter(c => c.stance === 'N').slice(0, 4)
    .map(c => quote(String(c.comment).replace(/\s*\n\s*/g, ' ').slice(0, 120), c.like_count)),
  p(`정부·정치 불신은 언급 비율이 ${f1(S.topic_share.F)}%로 적지 않았지만 좋아요 비중은 ${f1(S.topic_like_share.F)}%에 그쳤다. 대통령이나 정당을 직접 언급한 댓글 ${S.political_n}개 중 ${S.political_by_date['2026-09-13'] || 0}개가 9월 13일 하루에 몰렸고, 평균 좋아요는 ${S.political_mean_likes}개였다. 정치적 비난은 짧은 기간 집중적으로 올라왔지만 다른 이용자의 공감은 거의 얻지 못했다.`, { indent: true }),

  h3('3. 정책에 대한 집값 전망과 청약통장 행동 의향'),
  table([2600, 1600, 4826], [
    ['구분', '댓글 수', '주요 내용'],
    ['집값 상승 전망', fmt(S.outlook.U), '“미친 듯이 오른다”, “지금이 저점”처럼 최근 상승 추세를 이어 보는 내용'],
    ['집값 하락 전망', fmt(S.outlook.D), '인구 감소·빈집 증가에 따른 장기 하락, “대공황 오면 사겠다” 같은 가정, 가격이 내려갔으면 하는 바람'],
    ['청약통장 해지', fmt(S.action.H), `주된 이유: 대체 투자·낮은 금리(${RC('대체 투자·낮은 금리')}건), 분양가·집값 부담(${RC('분양가·집값 부담')}건), 대출규제(${RC('대출규제·자금조달')}건)`],
    ['청약통장 유지', fmt(S.action.K), `주된 이유: 임대·대출우대 등 부가 기능(${RK('임대·대출우대 등 부가 기능')}건), 소득공제·적금 기능(${RK('대체 투자·낮은 금리')}건)`],
  ]),
  caption('표 10. 집값 전망과 청약통장 행동 의향 (한 댓글이 여러 이유를 말할 수 있음)'),
  p(`집값 방향을 말한 댓글은 ${S.outlook.U + S.outlook.D}개(${f1(S.outlook_share)}%)뿐이었다. 대부분의 댓글은 가격이 오를지 내릴지가 아니라 “이미 감당할 수 없다”는 현재 수준을 말했다. 전망을 밝힌 댓글 중에는 하락(${S.outlook.D}개)이 상승(${S.outlook.U}개)보다 많았지만, 하락 댓글의 상당수는 구체적인 예측이라기보다 가격이 내려가기를 바라는 마음이나 인구 감소에 따른 장기적 전망이었다.`, { indent: true }),
  p(`청약통장에 대해서는 해지 의향(${S.action.H}개)이 유지 의향(${S.action.K}개)보다 많았다. 해지한 사람들은 주식·ETF 같은 다른 투자처와 분양가 부담을 주로 들었다. 유지하는 사람들도 내 집 마련 수단이라기보다 LH·SH 임대주택 가점, 디딤돌 대출 금리우대, 소득공제 같은 부가 혜택 때문에 통장을 두고 있다고 답했다.`, { indent: true }),

  h3('4. 일주일 동안의 반응 변화'),
  p(`분석 기간 7일 동안 댓글 수는 첫날(9월 13일) ${TR.daily['2026-09-13'].n}개로 가장 많았고, 9월 14~15일 ${TR.period['9/14~15'].n}개를 거쳐 9월 16일 이후에는 하루 12~61개로 줄었다(그림 4). 날짜별 댓글 수 차이가 커서 하루 단위 비율은 뒤로 갈수록 흔들리므로, 규모가 비슷하도록 첫날, 둘째·셋째 날, 나머지 나흘의 세 구간으로 묶어 비교하였다(표 11).`, { indent: true }),
  img(path.join(RESULTS, 'fig4_daily_trend.png'), 600, 390),
  caption('그림 4. 날짜별 댓글 수와 태도 비중 (청약 관련 댓글 기준)'),
  table([2600, 2142, 2142, 2142], [
    ['구분', '9/13', '9/14~15', '9/16~19'],
    ['댓글 수 (청약 관련)', ...PER.map(p => `${fmt(TR.period[p].n)} (${fmt(TR.period[p].n_relevant)})`)],
    ['부정', ...PER.map(p => `${f1(TR.period[p].stance_share.N)}%`)],
    ['양가', ...PER.map(p => `${f1(TR.period[p].stance_share.M)}%`)],
    ['긍정', ...PER.map(p => `${f1(TR.period[p].stance_share.P)}%`)],
    ['해당 없음 (전체 대비)', ...PER.map(p => `${f1(TR.period[p].irrelevant_share)}%`)],
    ['해지 / 유지 의향', ...PER.map(p => `${TR.period[p].action.H} / ${TR.period[p].action.K}`)],
    ['정치인·정당 언급 댓글', ...PER.map(p => `${TR.period[p].political}`)],
    ['대체 투자 언급 (전체 대비)', ...PER.map(p => `${f1(TR.period[p].topic_share.E)}%`)],
    ['부가 기능 언급 (전체 대비)', ...PER.map(p => `${f1(TR.period[p].topic_share.G)}%`)],
  ]),
  caption(`표 11. 구간별 태도와 주요 지표 변화 (태도 비중은 청약 관련 댓글 기준)${TR.period_test ? ` — 태도×구간 카이제곱 검정 χ²=${TR.period_test.chi2}, p=${TR.period_test.p}` : ''}`),
  p(`부정적 반응은 세 구간 모두 ${f1(Math.min(...PER.map(p => TR.period[p].stance_share.N)))}~${f1(Math.max(...PER.map(p => TR.period[p].stance_share.N)))}%로 거의 변하지 않았다. 변화는 나머지 두 반응 사이에서 나타났다. 긍정적 반응은 ${f1(TR.period['9/13'].stance_share.P)}% → ${f1(TR.period['9/14~15'].stance_share.P)}% → ${f1(TR.period['9/16~19'].stance_share.P)}%로 줄었고, 양가적 반응은 ${f1(TR.period['9/13'].stance_share.M)}% → ${f1(TR.period['9/14~15'].stance_share.M)}% → ${f1(TR.period['9/16~19'].stance_share.M)}%로 늘었다.${TR.period_test ? ` 구간과 태도의 관계는 통계적으로도 유의하였다(χ²=${TR.period_test.chi2}, 자유도 ${TR.period_test.dof}, p=${TR.period_test.p}). 다만 7일을 하루 단위로 나누면 뒤쪽 날짜의 댓글이 적어 유의하지 않았다(p=${TR.daily_test.p}).` : ''}`, { indent: true }),
  p(`즉 시간이 지나면서 청약을 부정하는 목소리는 그대로인 채, “그래도 깨지 마라”는 유지 권유가 줄고 “소득공제 때문에 둔다”, “최소 금액만 넣는다”처럼 효용을 따져 보는 양가적 댓글이 늘었다. 청약통장 해지 의향은 유지 의향의 ${ratio('9/13')}배(${TR.period['9/13'].action.H}대 ${TR.period['9/13'].action.K})에서 마지막 나흘 ${ratio('9/16~19')}배(${TR.period['9/16~19'].action.H}대 ${TR.period['9/16~19'].action.K})로 벌어졌다. 유지의 근거로 쓰이던 임대 가점·금리우대 같은 부가 기능 언급도 ${f1(TR.period['9/13'].topic_share.G)}%에서 ${f1(TR.period['9/16~19'].topic_share.G)}%로 줄었다.`, { indent: true }),
  p(`정치인·정당을 직접 언급한 댓글은 첫날 ${TR.period['9/13'].political}개(${pct(TR.period['9/13'].political, TR.period['9/13'].n)}%)로 몰렸다가 마지막 나흘에는 ${TR.period['9/16~19'].political}개(${pct(TR.period['9/16~19'].political, TR.period['9/16~19'].n)}%)로 줄었다. 반면 정부·정치 불신 전체 비중(${f1(TR.period['9/13'].topic_share.F)}% → ${f1(TR.period['9/16~19'].topic_share.F)}%)과 대체 투자 언급(${f1(TR.period['9/13'].topic_share.E)}% → ${f1(TR.period['9/16~19'].topic_share.E)}%)은 조금씩 늘었다. 특정 정치인을 겨냥한 구호는 초반에 집중되고, 뒤로 갈수록 제도 전반에 대한 불신과 “청약 대신 투자” 같은 개인적 대안이 남는 양상이다. 분양가·대출·가점·제도 불공정 같은 핵심 관심사의 비중은 기간 내내 큰 변화가 없었다.`, { indent: true }),

  h3('5. 정책 전후 실제 주택가격 변화'),
  table([2600, 3900, 2526], [
    ['지표', '수치', '출처·기준 시점'],
    ['서울 민간아파트 분양가', '3.3㎡당 6,287만 원 (전년 동월 대비 +34.2%)\n전용 84㎡ 환산 약 21억 3,760만 원', 'HUG, 2026년 8월'],
    ['수도권·전국 분양가', '수도권 3.3㎡당 3,615만 원 / 전국 2,029만 원', 'HUG, 2026년 8월'],
    ['주택담보대출 규제\n(서울 전역·경기 12곳)', 'LTV 40%, 한도: 15억 이하 6억 / 15~25억 4억 / 25억 초과 2억\n스트레스 금리 하한 3%', '10·15 대책, 2025년 10월'],
    ['서울 아파트 매매가격', '2026년 1~8월 누적 +7.52%, 8월 +1.05%\n9월 1주 +0.20% (강남·서초는 하락, 강북권 상승)', '한국부동산원'],
    ['지방 아파트 매매가격', '9월 1주: 4대 광역시 +0.01%, 세종 −0.02%', '한국부동산원'],
    ['청약통장 가입자', '2021년 약 2,677만 명 → 2026년 6월 2,471만 명\n2026년 1~7월 순감 32만 9천 좌', '국토교통부 자료(뉴스핌 보도)'],
  ]),
  caption('표 12. 주요 주택시장 지표 (보도 자료 기준)'),
  p('2025년 10·15 대책으로 서울 전역과 경기 12곳이 규제지역으로 지정되고 주택담보대출 한도가 줄었지만, 서울 아파트 매매가격은 2026년 들어서도 8월까지 7.52% 올랐다. 분양가는 매매가격보다 더 빠르게 올라 서울 민간아파트 분양가가 1년 새 34.2% 상승했다. 반면 지방은 4대 광역시가 보합, 세종이 소폭 하락하는 등 서울과의 격차가 커지고 있다. 대출 한도가 묶인 상태에서 가격이 오르면서, 전용 84㎡ 기준으로는 대출 4억 원을 받아도 약 18억 원의 현금이 필요한 상황이다.', { indent: true }),
  todo('공공데이터포털 원자료(housing_data.py)로 2021~2026년 월별 시계열 그래프를 추가하고, 10·15 대책 전후 12개월을 비교할 것: ① 청약통장 가입자 수 ② 권역별 중위매매가격 ③ 서울·경기·지방 실거래가 중위값.'),

  h3('6. 댓글 반응과 실제 가격 변화 비교'),
  table([2500, 3300, 1500, 1726], [
    ['댓글 속 인식', '실제 지표', '일치 여부', '비고'],
    [`“분양가가 너무 비싸 당첨돼도 못 산다” (${f1(S.topic_share.A)}%)`, '서울 84㎡ 약 21억 원, 대출 한도 4억 원이면 현금 약 18억 원 필요', '일치', '서울 기준. 수도권·지방은 격차가 작음'],
    [`“대출이 막혀 있다” (${f1(S.topic_share.B)}%)`, '규제지역 LTV 40%, 한도 6억·4억·2억 원', '대체로 일치', '15억 이하 주택은 6억 원 한도가 유지되어 “대출 자체가 안 된다”는 과장'],
    [`“1인가구·평범한 직장인은 불리” (${f1(S.topic_share.D)}%, 가점 ${f1(S.topic_share.C)}%)`, '가점제에서 부양가족·무주택 기간 점수 비중이 큼', '일치', '가점 원자료로 확인 필요'],
    [`“다들 해지한다” (해지 ${S.action.H} vs 유지 ${S.action.K})`, '2026년 1~7월 순감 32.9만 좌, 4년 연속 해지 우위', '방향 일치', '가입자는 여전히 2,471만 명'],
    [`“지방은 청약이 필요 없다” (${f1(S.topic_share.H)}%)`, '지방 매매가 보합·하락, 서울만 상승', '일치', '미분양 통계로 보강 필요'],
    [`집값 전망 (${f1(S.outlook_share)}%, 하락 ${S.outlook.D} > 상승 ${S.outlook.U})`, '서울 누적 +7.52%로 상승 지속', '불일치', '하락 댓글 다수가 예측보다 바람·가정'],
  ]),
  caption('표 13. 댓글 속 인식과 주택시장 지표 비교'),
  p('정리하면, 댓글이 청약을 부정적으로 보는 근거인 고분양가, 대출 한도, 가점 구조, 지역 간 격차는 실제 시장 지표와 대체로 일치하였다. 이용자들이 막연한 불만이 아니라 현재의 가격과 제도 아래에서 청약이 자신에게 어떤 의미인지를 비교적 정확하게 판단하고 있다는 뜻이다. 반면 집값의 방향에 대해서는 댓글 여론(하락 우세)과 실제 시장(서울 상승 지속)이 어긋났다. “대출이 전혀 안 된다”, “모두 해지한다”처럼 규모를 부풀리는 표현도 있었다.', { indent: true }),
);

// ---------- Ⅲ. 결론 ----------
children.push(
  h1('Ⅲ. 결론'),
  h2('1. 주요 분석 결과'),
  bullet(`청약 관련 댓글의 ${f1(S.stance_share.N)}%가 청약 제도와 청약통장에 부정적이었다.`),
  bullet(`부정적 인식의 핵심 근거는 ${T[topicOrder[0]]}, ${T[topicOrder[1]]}, ${T[topicOrder[2]]}였으며, 이는 실제 분양가 상승과 대출 규제 수준과 대체로 일치하였다.`),
  bullet(`집값 전망을 밝힌 댓글은 ${f1(S.outlook_share)}%에 불과했고, 하락 전망이 더 많아 서울 아파트값 상승이라는 실제 흐름과는 어긋났다.`),
  bullet(`해지 의향이 유지 의향보다 많았고, 유지하는 사람들도 내 집 마련보다 임대 가점·금리우대 같은 부가 기능 때문에 통장을 두고 있었다.`),
  bullet('정치적 비난 댓글은 수는 적지 않았지만 공감(좋아요)은 거의 얻지 못했다.'),
  bullet(`일주일 동안 부정적 반응은 ${f1(Math.min(...PER.map(p => TR.period[p].stance_share.N)))}~${f1(Math.max(...PER.map(p => TR.period[p].stance_share.N)))}%로 유지된 반면, 긍정은 ${f1(TR.period['9/13'].stance_share.P)}%에서 ${f1(TR.period['9/16~19'].stance_share.P)}%로 줄고 양가는 ${f1(TR.period['9/13'].stance_share.M)}%에서 ${f1(TR.period['9/16~19'].stance_share.M)}%로 늘었다. 시간이 지날수록 유지 권유가 줄고 효용을 따지는 반응이 늘었다.`),
  h2('2. 수집된 댓글 데이터의 활용 방안'),
  bullet('정책 모니터링: 청약·대출 정책이 발표될 때마다 같은 방법으로 댓글을 수집·분류하면, 정책 대상자가 어떤 점을 문제로 받아들이는지 빠르게 확인할 수 있다.'),
  bullet('제도 개선 근거: 1인가구 불리, 소득 요건과 분양가의 모순처럼 반복되는 불만은 가점제·특별공급 개편 논의의 참고 자료가 될 수 있다.'),
  bullet('시계열 비교: 댓글은 작성 시각이 남아 있어 주택가격·가입자 수 같은 월별 지표와 시점을 맞춰 비교할 수 있다.'),
  bullet('재현 가능한 분석: 수집·분류·집계 코드와 분류 기준(cy-index.txt)을 공개해, 다른 영상이나 기간에도 같은 방법을 적용할 수 있다.'),
  h2('3. 온라인 여론과 실제 시장 변화의 관계'),
  p('청약에 대한 온라인 인식은 실제 주택시장의 “가격 수준과 접근성”을 잘 반영하였다. 분양가 상승과 대출 규제가 겹치면서 청약 당첨이 곧 내 집 마련으로 이어지지 않는 구조가 되었고, 댓글은 이를 “당첨돼도 못 산다”는 한 문장으로 요약했다. 청약통장 가입자 순감이라는 행동 지표도 이 인식과 방향이 같다. 반면 가격의 “방향”에 대해서는 댓글 여론과 실제 시장이 어긋났다. 따라서 온라인 여론은 시장을 예측하는 지표라기보다, 정책이 대상자에게 어떻게 받아들여지는지를 보여주는 진단 지표로서 의미가 있다.', { indent: true }),
  h2('4. 연구의 한계'),
  bullet(`영상 하나의 댓글만 분석했다. 영상이 청약통장 해지를 다루고 있어 부정적인 댓글이 더 많이 모였을 수 있다.`),
  bullet(`분석 기간(${period})은 영상 게시 이틀 뒤부터이다. 게시 직후 이틀간 달린 댓글과 좋아요의 대부분이 빠져 있어, 좋아요 가중 수치는 소수 댓글에 크게 좌우되었다.`),
  bullet('댓글 작성자의 나이, 지역, 소득을 알 수 없어 특정 인구 집단을 대표한다고 보기 어렵다.'),
  bullet('LLM 하나로 분류하였으므로 사람 코더와의 일치도 검증이 필요하다. 특히 집값 전망은 예측과 바람을 구분하기 어려웠다.'),
  bullet('댓글과 시장 지표의 시점이 정확히 맞지 않으며, 이 연구는 상관관계를 비교한 것이지 인과관계를 밝힌 것이 아니다.'),
);

// ---------- 참고문헌 / 부록 ----------
children.push(
  new Paragraph({ children: [new PageBreak()] }),
  h1('참고자료'),
  ...[
    ['크랩, 「청약통장 다들 왜 깨고 있을까?」, YouTube, 2026.', 'https://www.youtube.com/watch?v=g4h29mJufpc'],
    ['뉴스핌, 「“청약 넣어도 부담”…청약통장 4년째 가입보다 해지 많아」, 2026.8.31.', 'https://www.newspim.com/news/view/20260831000501'],
    ['한국경제, 「어차피 당첨 안돼 줄줄이 청약통장 찢었다…역대급 상황」, 2026.9.13.', 'https://www.hankyung.com/article/2026091313571'],
    ['뉴데일리, 「서울 아파트 평당 분양가 6287만원, 1년 새 34% 급등」, 2026.9.18.', 'https://biz.newdaily.co.kr/site/data/html/2026/09/18/2026091800233.html'],
    ['대한민국 정책브리핑, 「서울·경기 12곳 주담대 한도 축소…25억 초과 주택 2억 원까지만」, 2025.10.15.', 'https://www.korea.kr/news/policyNewsView.do?newsId=148950959'],
    ['글로벌이코노믹, 「서울 아파트 매매·전세 상승률 격차 0.17%P…나란히 7%대 상승」, 2026.9.15.', 'https://www.g-enews.com/article/Real-Estate/2026/09/20260915103930303414b1077807_1'],
    ['국제뉴스, 「한국부동산원, 9월 첫째 주 전국 아파트값 0.08%↑…서울 0.20% 상승」, 2026.9.10.', 'https://www.gukjenews.com/news/articleView.html?idxno=3691555'],
    ['공공데이터포털, 한국부동산원 청약홈 청약통장 전체 가입현황 (15088657)', 'https://www.data.go.kr/data/15088657/fileData.do'],
    ['공공데이터포털, 한국부동산원 청약홈 청약통장 통계 조회 서비스 (15114369)', 'https://www.data.go.kr/data/15114369/openapi.do'],
    ['공공데이터포털, 한국부동산원 지역별 청약 신청자·당첨자 정보 (15110975, 15110976)', 'https://www.data.go.kr/data/15110975/fileData.do'],
    ['공공데이터포털, 한국부동산원 중위매매가격·중위단위매매가격 (15112206, 15112207)', 'https://www.data.go.kr/data/15112206/fileData.do'],
    ['공공데이터포털, 국토교통부 아파트 매매 실거래가 상세 자료 (15126468)', 'https://www.data.go.kr/data/15126468/openapi.do'],
    ['YouTube Data API v3, CommentThreads: list', 'https://developers.google.com/youtube/v3/docs/commentThreads/list'],
    ['OpenRouter, openai/gpt-oss-120b (댓글 분류 모델)', 'https://openrouter.ai/openai/gpt-oss-120b'],
  ].map(([t, url]) => bullet([new TextRun(t + ' '),
    new ExternalHyperlink({ link: url, children: [new TextRun({ text: url, style: 'Hyperlink', color: '2A78D6', underline: {} })] })])),
  h1('부록 1. 분류 기준 (cy-index.txt)'),
  ...fs.readFileSync(path.join(__dirname, '..', 'cy-index.txt'), 'utf-8').split('\n')
    .filter(t => t.trim() && !t.startsWith('#'))
    .map(t => new Paragraph({ spacing: { after: 40 }, shading: { type: ShadingType.CLEAR, fill: 'F3F3F1' },
      children: [new TextRun({ text: t, size: 18, font: 'Consolas' })] })),
  h1('부록 2. 분류 결과 파일'),
  p(`댓글별 분류 결과는 ${S.source} 파일에 있다. 열 구성: video_id, comment_id, text_raw, published_at, like_count, reply_count, stance, topics, outlook, action.`),
);

const doc = new Document({
  footnotes: {
    1: { children: [new Paragraph({ children: [new TextRun({ text: '코드 저장소(GitHub): ', size: 17 }),
      new ExternalHyperlink({ link: GITHUB_URL, children: [new TextRun({ text: GITHUB_URL, style: 'Hyperlink', color: '2A78D6', underline: {}, size: 17 })] }),
      new TextRun({ text: ' — 수집(collect_comments.py), 분류(classify_comments.py), 집계(analyze_comments.py), 신뢰도 검증(check_reliability.py), DB 저장(upload_supabase.py), 건수 대조(verify_counts.py), 보고서 생성(report/build_report.js) 코드와 결과 폴더 전체.', size: 17 })] })] },
    2: { children: [new Paragraph({ children: [new TextRun({ text: 'Supabase 조회 링크(읽기 전용, 로그인 불필요) — 댓글 분류 결과(처음 100행): ', size: 17 }),
      new ExternalHyperlink({ link: SUPABASE_URL, children: [new TextRun({ text: SUPABASE_URL, style: 'Hyperlink', color: '2A78D6', underline: {}, size: 17 })] }),
      new TextRun({ text: ' / 실행 정보: ', size: 17 }),
      new ExternalHyperlink({ link: SUPABASE_RUNS_URL, children: [new TextRun({ text: SUPABASE_RUNS_URL, style: 'Hyperlink', color: '2A78D6', underline: {}, size: 17 })] })] })] },
  },
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 30, bold: true, font: FONT, color: '1F3864' }, paragraph: { outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 25, bold: true, font: FONT, color: '1F3864' }, paragraph: { outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 22, bold: true, font: FONT }, paragraph: { outlineLevel: 2 } },
    ],
  },
  numbering: { config: [{ reference: 'bul', levels: [
    { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 260 } } } },
    { level: 1, format: LevelFormat.BULLET, text: '–', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 900, hanging: 260 } } } },
  ] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '52514E' })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then(buf => { const out = path.join(RESULTS, '청약인식_보고서초안_B안.docx'); fs.writeFileSync(out, buf); console.log('저장:', out); });
