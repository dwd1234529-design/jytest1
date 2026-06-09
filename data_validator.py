import re
import math
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import numpy as np
# ----------------------------------------------------------------------
# KoNLPy Okt 형태소 분석기 연동 및 Java 환경 부재 대비 Fallback 모듈 정의
# ----------------------------------------------------------------------
class FallbackOkt:
    """
    로컬 시스템에 Java Development Kit (JDK)이 설치되어 있지 않거나
    KoNLPy 연동에 실패했을 때 작동하는 정밀 규칙 기반의 Fallback 형태소 분석기입니다.
    조사, 어미, 접사 등을 정규식 사전으로 검출하여 형태소 수준으로 텍스트를 분할합니다.
    """
    def __init__(self):
        # 한국어 대표 조사 리스트
        self.particles = [
            '은', '는', '이', '가', '을', '를', '의', '에', '에게', '에서', 
            '와', '과', '으로', '로', '도', '만', '까지', '마저', '조차', '부터', '나', '이나'
        ]
        # 대표 연결/종결 어미 패턴
        self.endings = [
            '다', '요', '며', '고', '게', '어', '아', '지', '네', '어라', '아라', '자', '소서',
            '습니다', '니다', '해요', '지요', '고요', '면서', '며', '으나', '지만', '는데'
        ]
        
    def morphs(self, text: str) -> List[str]:
        # 1. 특수문자 제거 및 어절 단위 분할
        cleaned_text = re.sub(r'[^\w\s]', '', text)
        words = cleaned_text.split()
        morphemes = []
        
        for word in words:
            if not word:
                continue
            
            matched = False
            # 조사 분리 시도 (어절 뒤에서부터 매칭)
            for p in sorted(self.particles, key=len, reverse=True):
                if word.endswith(p) and len(word) > len(p):
                    stem = word[:-len(p)]
                    morphemes.append(stem)
                    morphemes.append(p)
                    matched = True
                    break
            
            if not matched:
                # 어미 분리 시도
                for e in sorted(self.endings, key=len, reverse=True):
                    if word.endswith(e) and len(word) > len(e):
                        stem = word[:-len(e)]
                        morphemes.append(stem)
                        morphemes.append(e)
                        matched = True
                        break
                        
            if not matched:
                # 일반 명사/동사 어근으로 취급
                morphemes.append(word)
                
        return morphemes
# KoNLPy Okt 로드 시도
try:
    from konlpy.tag import Okt
    # JVM 초기화가 실제로 발생하는지 가볍게 테스트
    okt_analyzer = Okt()
    okt_analyzer.morphs("테스트")
    USING_KONLPY = True
    print("[SYSTEM] KoNLPy Okt 형태소 분석기가 정상 작동합니다.")
except Exception as e:
    # JVM이나 JDK 미설치 등으로 실패할 경우 Fallback 로드
    okt_analyzer = FallbackOkt()
    USING_KONLPY = False
    print(f"[SYSTEM] KoNLPy 로드 실패 ({str(e)}). 규칙 기반 FallbackOkt 엔진을 활성화합니다.")
# ----------------------------------------------------------------------
# FastAPI 앱 설정
# ----------------------------------------------------------------------
app = FastAPI(
    title="Natural Argument Essay Analysis Engine",
    description="대학생들의 자연스러운 논증문 작성을 돕는 9대 채점 및 문체 연산 API 서버",
    version="1.0.0"
)
# CORS 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ----------------------------------------------------------------------
# 데이터 모델 정의
# ----------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    text: str
class HighlightItem(BaseModel):
    start: int
    end: int
    type: str       # 'translation_style' (AI 번역투), 'assertion' (지나친 단정), 'style_issue' (비학술적)
    text: str
    tip: str
class MetricScore(BaseModel):
    score: float
    description: str
class AnalyzeResponse(BaseModel):
    # 4대 필수 계량 문체 지표
    std_sentence_length: float
    word_ttr: float
    morpheme_ttr: float
    total_hedge_density: float
    
    # AI스러운 문체 탐지 피드백 요약
    ai_sentence_warning: bool
    ai_sentence_feedback: str
    ai_word_warning: bool
    ai_word_feedback: str
    
    # 9대 채점 기준 점수 (1.0 ~ 5.0) 및 코멘트 (구체화된 한글 명칭)
    scores: Dict[str, MetricScore]
    total_average: float
    grade: str
    grade_commentary: str  # 강점 격려 및 취약 영역 집중 보완 연계형 동적 한줄평
    
    # 에세이 교정용 하이라이트 문장 리스트
    highlights: List[HighlightItem]
    
    # 부가 정보
    char_count: int
    word_count: int
    sentence_count: int
    paragraph_count: int
    using_konlpy: bool
# ----------------------------------------------------------------------
# 핵심 분석 및 계산 로직
# ----------------------------------------------------------------------
def split_sentences(text: str) -> List[str]:
    """텍스트를 문장 단위로 분절합니다."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s.strip()]
def get_paragraphs(text: str) -> List[str]:
    """텍스트를 문단 단위로 분절합니다."""
    paragraphs = re.split(r'\n+', text)
    return [p.strip() for p in paragraphs if p.strip()]
def calculate_std_sentence_length(sentences: List[str]) -> float:
    """문장별 어절 수의 표준편차를 구합니다."""
    if not sentences:
        return 0.0
    lengths = [len(s.split()) for s in sentences]
    return float(np.std(lengths))
def calculate_word_ttr(text: str) -> float:
    """총 어절 수 대비 고유 어절 수의 비율을 구합니다 (어절 다양성)."""
    cleaned = re.sub(r'[^\w\s]', '', text)
    words = cleaned.split()
    if not words:
        return 0.0
    unique_words = set(words)
    return float(len(unique_words) / len(words))
def calculate_morpheme_ttr(text: str) -> float:
    """전체 형태소 수 대비 고유 형태소 수의 비율을 구합니다 (형태소 다양성)."""
    try:
        morphs = okt_analyzer.morphs(text)
        if not morphs:
            return 0.0
        return float(len(set(morphs)) / len(morphs))
    except Exception:
        return 0.5
def calculate_hedge_density(text: str, total_words: int) -> float:
    """1,000어절당 완화 표현의 빈도수를 계산합니다."""
    if total_words == 0:
        return 0.0
    
    hedge_expressions = [
        '것으로 보인다', '라 할 수 있다', '라고 생각한다', 
        '수 있다', '인 것 같다', '임을 알 수 있다', 
        '할 필요가 있다', '해야 할 것이다'
    ]
    
    total_count = 0
    for expr in hedge_expressions:
        pattern = r'\s*'.join(re.escape(word) for word in expr.split())
        matches = re.findall(pattern, text)
        total_count += len(matches)
        
    return float((total_count / total_words) * 1000)
# ----------------------------------------------------------------------
# API 라우트
# ----------------------------------------------------------------------
@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze_essay(request: AnalyzeRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="텍스트 내용이 비어 있습니다.")
        
    # 기본 통계량
    char_count = len(text)
    paragraphs = get_paragraphs(text)
    paragraph_count = len(paragraphs)
    sentences = split_sentences(text)
    sentence_count = len(sentences)
    
    # 어절(단어) 추출
    words = re.sub(r'[^\w\s]', '', text).split()
    word_count = len(words)
    
    # 공백 제외 글자수 기준 (최소 2문장, 공백 제외 30자 이상)
    char_count_no_space = len(text.replace(" ", "").replace("\n", "").replace("\r", ""))
    if char_count_no_space < 30 or sentence_count < 2:
        raise HTTPException(
            status_code=400, 
            detail="분석을 위해 최소 2문장, 공백 제외 30자 이상의 완성도 있는 논증문을 입력해주세요."
        )
        
    # 4대 필수 지표 연산
    std_sentence_length = calculate_std_sentence_length(sentences)
    word_ttr = calculate_word_ttr(text)
    morpheme_ttr = calculate_morpheme_ttr(text)
    total_hedge_density = calculate_hedge_density(text, word_count)
    
    # ------------------------------------------------------------------
    # AI스러운 문체 시각 경고 가이드라인 계산
    # ------------------------------------------------------------------
    ai_sentence_warning = False
    ai_sentence_feedback = ""
    if std_sentence_length < 5.0:
        ai_sentence_warning = True
        ai_sentence_feedback = "현재 문장들의 길이와 구조가 다소 일정하여, 독자에게 기계적인 인상을 줄 수 있습니다. 생각의 흐름에 맞춰 짧은 문장과 긴 문장을 다채롭게 섞어 쓰면 글의 활력이 살아납니다."
        
    ai_word_warning = False
    ai_word_feedback = ""
    if word_ttr >= 0.81:
        ai_word_warning = True
        ai_word_feedback = "단어들이 다채롭게 사용되었으나 사전식 나열에 가깝습니다. 핵심 주제 키워드를 자연스럽게 맥락 속에서 반복하며 일관된 방향으로 전개해 보세요."
    # ------------------------------------------------------------------
    # 하이라이트 영역 감지 로직 (번역투, 지나친 단정, 비학술성)
    # ------------------------------------------------------------------
    highlights: List[HighlightItem] = []
    
    # 1) AI 번역투/기계적 표현 사전
    translation_rules = [
        (r'에\s*있어서의', "AI 번역투 표현 (~에 있어서의 -> ~의 / ~에 관한)"),
        (r'에\s*의해\s*행해지다', "수동적 번역 표현 (~에 의해 행해지다 -> ~가 수행하다)"),
        (r'가짐에\s*틀림없다', "부자연스러운 번역투 조동사 표현 (~가짐에 틀림없다 -> ~임이 분명하다)"),
        (r'생각되어진다', "이중 피동형 문장 (생각되어진다 -> 생각된다 / 판단한다)"),
        (r'보여진다', "이중 피동형 문장 (보여진다 -> 보인다)"),
        (r'우리는\s+\w*(해야\s*한다|할\s*필요가\s*있다)', "AI 특유의 교시적/공허한 의무문 표현 (우리는 ~해야 한다 -> 주어를 명확히 하고 능동태로 고쳐보세요)")
    ]
    
    # 2) 지나치게 단정적인 표현 (학술적 신뢰성 결여 및 AI 특유의 확신)
    assertion_rules = [
        (r'결코', "지나친 단정 표현 (학술문에서는 예외 가능성을 열어두는 완곡한 전개가 좋습니다)"),
        (r'무조건', "지나친 극단적 어휘 (무조건 -> 타당하게 / 상황에 따라)"),
        (r'절대', "지나친 극단적 어휘 (절대 -> 대체로 / 사실상)"),
        (r'반드시', "단정적 확신 표현 (반드시 -> ~할 여지가 크다 / ~로 해석된다)"),
        (r'100%', "비학술적 단정 수치 (100% -> 압도적으로 / 높은 확률로)")
    ]
    # 3) 비학술적/구어체 표현
    colloquial_rules = [
        (r'\b(요|죠)\b[.!?]', "논증문에 어울리지 않는 구어체 종결어미 (요/죠 -> ~다)"),
        (r'\b(했어요|했죠|합니다만)\b', "구어체 동사 활용 (했어요 -> 하였다 / 진행했다)"),
        (r'\b(진짜|되게|엄청|겁나|넘)\b', "구어체 수식어 사용 (지양하고 '매우', '현저히', '상당히' 등으로 교체하세요)"),
        (r'\b(해서|했음|했슴|음)\b[.!?]', "명사형/약식 종결 종결어미 (논증문에서는 명확한 서술어 '~다.'로 마쳐야 합니다)")
    ]
    def find_patterns(pattern_list, type_name):
        for pattern, tip in pattern_list:
            for match in re.finditer(pattern, text):
                highlights.append(HighlightItem(
                    start=match.start(),
                    end=match.end(),
                    type=type_name,
                    text=match.group(),
                    tip=tip
                ))
    find_patterns(translation_rules, 'translation_style')
    find_patterns(assertion_rules, 'assertion')
    find_patterns(colloquial_rules, 'style_issue')
    
    highlights.sort(key=lambda x: x.start)
    # ------------------------------------------------------------------
    # 9대 채점 기준 점수 계산 로직 (구체적 한글화 명칭으로 매핑)
    # ------------------------------------------------------------------
    scores: Dict[str, MetricScore] = {}
    # --- 1. [표현1] 문장 및 어휘의 자연스러움 (1~5점) ---
    if std_sentence_length <= 4.5 or word_ttr >= 0.81:
        expr1_score = 1.5 if (std_sentence_length <= 4.0 or word_ttr >= 0.83) else 2.0
        expr1_desc = "글 속 문장들의 어절 길이 편차가 비교적 균일하여 단조로운 인상을 주거나, 고유 어절 비율이 다소 높아 핵심 주제가 문맥 속에 부드럽게 녹아들기 어려울 수 있습니다. 생각의 흐름에 맞춰 문장 길이에 변화를 주고 핵심 주제어를 자연스럽게 반복해 보세요."
        # 요구사항 3 (메시지 직관화 반영)
        expr1_desc = "모든 문장의 길이가 비슷비슷해서 글이 다소 단조롭게 느껴지거나, 어려운 낱말을 무리하게 나열하여 핵심 내용이 한눈에 들어오지 않을 수 있습니다. 생각의 흐름에 따라 긴 문장과 짧은 문장을 골고루 섞어 쓰고, 중요한 중심 단어는 자연스럽게 반복하여 일관성을 높여 보세요."
    elif std_sentence_length >= 5.5 and (0.75 <= word_ttr <= 0.78):
        expr1_score = 5.0 if std_sentence_length >= 6.2 else 4.5
        expr1_desc = "글 고유의 다채롭고 역동적인 문장 길이 편차(5.5 이상)와 글쓴이만의 핵심어가 자연스럽게 강조·순환되는 고유 어절 구조(0.75~0.78)가 매우 조화롭습니다. 읽기 편안하고 자연스러운 글쓰기 흐름을 잘 보여주고 있습니다."
    else:
        base = 3.0
        if 4.5 < std_sentence_length < 5.5:
            base += (std_sentence_length - 4.5) * 0.5
        elif std_sentence_length >= 5.5:
            base += 0.5
            
        if 0.78 < word_ttr < 0.81:
            base -= (word_ttr - 0.78) * 15
        elif word_ttr < 0.75:
            base -= (0.75 - word_ttr) * 5
            
        expr1_score = max(2.5, min(3.8, base))
        expr1_desc = "전반적으로 무난한 문장 흐름을 갖추었으나, 글에 생동감을 불어넣기 위해 문장 구조의 변주를 시도하고 단어 배치를 조금 더 자연스럽게 다듬는 것을 권장합니다."
        # 요구사항 4 (용어 순화 반영)
        expr1_desc = "전반적으로 무난한 흐름이지만, 글을 더 생동감 있게 만들려면 문장 길이를 다양하게 바꾸고 어색한 단어 연결을 자연스럽게 다듬는 것이 좋습니다."
        
    scores['문장 및 어휘의 자연스러움'] = MetricScore(score=round(expr1_score, 1), description=expr1_desc)
    # --- 2. [내용5] 반론 고려 및 신중한 표현 (1~5점) ---
    # 요구사항 9 (완화 표현 밀도 산출 알고리즘 동적 스케일링 적용)
    if word_count < 500:
        # 단문일수록 scaling factor가 증가하여 임계치를 동적으로 비례 조절(Scaling)
        scaling_factor = 1.0 + (500 - word_count) / 300.0
    else:
        scaling_factor = 1.0
    opt_min = 7.0 / scaling_factor
    opt_max = 9.0 * scaling_factor
    over_limit = 11.0 * scaling_factor
    under_limit = 4.0 / scaling_factor
    refutation_words = ['물론', '반면', '일각에서는', '반대 의견', '혹자는', '비록']
    has_refutation = any(word in text for word in refutation_words)
    
    if (opt_min <= total_hedge_density <= opt_max) and std_sentence_length >= 5.5:
        content5_score = 5.0 if has_refutation else 4.3
        content5_desc = "1,000어절당 완화 표현 밀도가 조화로우며 문장 호흡의 다양성(5.5 이상) 또한 함께 살아있어, 자신의 주장을 신중하고 설득력 있게 펼치는 성숙한 논조를 훌륭하게 보여주고 있습니다."
    else:
        if total_hedge_density > over_limit:
            content5_score = 2.5
            content5_desc = "완화 어구(~로 보인다, ~일 수 있다)가 너무 빈번히 사용되어 주장의 선명도가 다소 낮아지거나 문장이 다소 경직된 인상을 줄 수 있습니다. 자신의 요지를 보다 자신감 있고 명확하게 제기해 보는 연습을 해보세요."
        elif total_hedge_density < under_limit:
            content5_score = 2.0
            content5_desc = "논증이 다소 단정적으로 흘러 독자의 반론을 수용할 여지가 부족할 수 있습니다. 완화 어구(~로 해석된다, ~할 여지가 크다)를 적절히 활용하여 신중하고 설득력 있는 논조를 보완해 보세요."
        else:
            content5_score = 3.5 if has_refutation else 3.0
            content5_desc = "완화 표현의 밀도는 비교적 양호하나, 문장의 흐름을 더 유연하게 다듬고 상대방의 반론도 사려 깊게 포용해 주는 글쓰기 구조를 보완하기를 추천합니다."
            
    scores['반론 고려 및 신중한 표현'] = MetricScore(score=round(content5_score, 1), description=content5_desc)
    # 3. [내용1] 문제 상황 제시 및 정보성 (1~5점)
    intro_p = paragraphs[0] if paragraph_count > 0 else ""
    intro_keywords = ['문제', '논란', '현상', '갈등', '최근', '실태', '현실', '상황', '어려움', '부각']
    intro_score_factor = sum(1 for kw in intro_keywords if kw in intro_p)
    content1_score = min(5.0, max(1.5, 2.0 + (intro_score_factor * 0.4) + (len(intro_p) / 200)))
    content1_desc = "서론에서 당면한 구체적인 문제 상황과 갈등 지점을 밀도 높은 배경 정보와 키워드로 분명하게 제기하여 서두의 정보성이 우수합니다." if content1_score >= 4.0 else "서론의 문제제기가 분량 면에서 다소 짧거나 갈등 양상이 흐릿합니다. 독자가 현안의 중요성을 즉각 체감할 수 있도록 구체적인 통계나 실태 배경을 보강해 주세요."
    scores['문제 상황 제시 및 정보성'] = MetricScore(score=round(content1_score, 1), description=content1_desc)
    content1_score = round(content1_score, 1)
    
    # 요구사항 6 (3단계 세분화)
    if content1_score < 2.5:
        content1_desc = "서론에서 문제제기가 전혀 이루어지지 않았거나 매우 모호합니다. 독자의 이목을 끌 수 있도록 문제 상황과 사회적 배경 정보를 대폭 보강해 주세요."
    elif content1_score < 4.0:
        content1_desc = "서론의 문제제기가 분량 면에서 다소 짧거나 갈등 양상이 흐릿합니다. 독자가 현안의 중요성을 체감할 수 있도록 구체적인 실태 배경이나 통계를 보완해 보세요."
    else:
        content1_desc = "서론에서 당면한 구체적인 문제 상황과 갈등 지점을 밀도 높은 배경 정보와 키워드로 분명하게 제기하여 서두의 정보성이 우수합니다."
        
    scores['문제 상황 제시 및 정보성'] = MetricScore(score=content1_score, description=content1_desc)
    # 4. [내용2] 주장의 명료성과 일관성 (1~5점)
    claim_keywords = ['해야 한다', '필요하다', '요구된다', '생각한다', '바람직하다', '타당하다']
    claim_matches = sum(len(re.findall(k, text)) for k in claim_keywords)
    outro_p = paragraphs[-1] if paragraph_count > 1 else ""
    common_nouns_factor = 0.5 if (outro_p and len(set(intro_p.split()) & set(outro_p.split())) >= 3) else 0.0
    content2_score = min(5.0, max(1.5, 2.5 + (0.3 if claim_matches >= 2 else 0.0) + (common_nouns_factor * 3)))
    content2_desc = "핵심적인 주장이 명시적인 문장 형태로 서술되어 있고, 서론에서 제기한 질문과 결론의 해답이 일관된 논지로 유기적으로 잘 대응합니다." if content2_score >= 4.0 else "글의 서론-본론-결론이 흐트러짐 없이 하나의 논지로 수렴하는지 일관성을 점검해야 합니다. 자신의 중심 생각을 한 문장으로 명료하게 수정한 후 글 전반에 반영해 보세요."
    scores['주장의 명료성과 일관성'] = MetricScore(score=round(content2_score, 1), description=content2_desc)
    content2_score = round(content2_score, 1)
    # 요구사항 6 (3단계 세분화)
    if content2_score < 2.5:
        content2_desc = "주제가 명확하지 않거나 무엇을 주장하는지 파악하기 어렵습니다. 주장하는 요지를 선명한 한 문장의 완성된 형태로 명시하여 글의 뼈대를 다시 세워보세요."
    elif content2_score < 4.0:
        content2_desc = "글의 서론-본론-결론이 흐트러짐 없이 하나의 논지로 수렴하는지 일관성을 점검해야 합니다. 중심 생각을 한 문장으로 다듬어 글 전반에 일관되게 녹여보세요."
    else:
        content2_desc = "핵심적인 주장이 명시적인 문장 형태로 서술되어 있고, 서론에서 제기한 질문과 결론의 해답이 일관된 논지로 유기적으로 잘 대응합니다."
        
    scores['주장의 명료성과 일관성'] = MetricScore(score=content2_score, description=content2_desc)
    # 5. [내용3] 논거의 설득력과 적절성 (1~5점)
    reason_keywords = ['왜냐하면', '기 때문이다', '이유는', '근거로', '때문이다']
    citation_keywords = ['연구', '통계', '조사', '분석', '자료', '뉴스', '보고서', '수치']
    reason_matches = sum(len(re.findall(k, text)) for k in reason_keywords)
    citation_matches = sum(len(re.findall(k, text)) for k in citation_keywords)
    content3_score = min(5.0, max(1.5, 2.0 + (reason_matches * 0.4) + (citation_matches * 0.3)))
    content3_desc = "주장을 뒷받침할 수 있는 합리적인 사실적 논거와 객관적인 신뢰성 높은 인용(조사 연구, 통계 자료 등)이 적절히 잘 구성되어 있습니다." if content3_score >= 4.0 else "단순히 글쓴이의 주관적 견해만 반복되고 있습니다. '왜냐하면'을 활용한 논리적 인과 서술과 학계의 전문 지표, 신문 자료 등 공신력 있는 외부 논거를 추가해 논증력을 갖춰 주세요."
    scores['논거의 설득력과 적절성'] = MetricScore(score=round(content3_score, 1), description=content3_desc)
    content3_score = round(content3_score, 1)
    # 요구사항 6 (3단계 세분화)
    if content3_score < 2.5:
        content3_desc = "주장에 대한 객관적 증명이 결여되어 주관적인 독백에 그치고 있습니다. 신뢰할 수 있는 외부 통계 자료나 연구 성과 등의 객관적 논거를 필수적으로 보강해야 합니다."
    elif content3_score < 4.0:
        content3_desc = "단순히 글쓴이의 주관적 견해만 반복되는 경향이 있습니다. 실제 사례나 통계 지표 등 객관적인 외부 논거를 추가하여 주장의 신뢰도를 높여보세요."
    else:
        content3_desc = "주장을 뒷받침할 수 있는 합리적인 사실적 논거와 객관적인 신뢰성 높은 인용(조사 연구, 통계 자료 등)이 적절히 잘 구성되어 있습니다."
        
    scores['논거의 설득력과 적절성'] = MetricScore(score=content3_score, description=content3_desc)
    # 6. [내용4] 논리 전개의 충분성 (1~5점)
    body_paragraphs = paragraphs[1:-1] if paragraph_count > 2 else paragraphs[1:]
    long_body_count = sum(1 for p in body_paragraphs if len(p) >= 250)
    content4_score = min(5.0, max(1.0, 1.5 + (long_body_count * 1.0) + (len(body_paragraphs) * 0.3)))
    content4_desc = "본론 문단이 구체적인 하위 주장들로 짜임새 있게 구성되어 논리적 전개의 충분성과 분석적 깊이가 우수합니다." if content4_score >= 4.0 else "소주제를 뒷받침하는 설명이 표면적인 수준에서 끊기거나 본론 문단이 지나치게 비약적으로 서술되었습니다. 소론을 더욱 세밀하게 전개해 가며 글의 충실도를 확보하세요."
    scores['논리 전개의 충분성'] = MetricScore(score=round(content4_score, 1), description=content4_desc)
    content4_score = round(content4_score, 1)
    # 요구사항 6 (3단계 세분화) 및 요구사항 5 (메시지 직관화 반영)
    if content4_score < 2.5:
        content4_desc = "본론의 서술이 매우 거칠고 생략이 심해 논리적 흐름이 끊깁니다. 하위 문단마다 구체적인 설명과 풍부한 세부 내용을 덧붙여 논리적 비약을 메워주어야 합니다."
    elif content4_score < 4.0:
        content4_desc = "소주제를 뒷받침하는 설명이 부족하거나, 본론의 이야기가 갑자기 건너뛰듯 서술되었습니다. 세부 내용을 더 구체적으로 덧붙여 글의 깊이와 분량을 채워보세요."
    else:
        content4_desc = "본론 문단이 구체적인 하위 주장들로 짜임새 있게 구성되어 논리적 전개의 충분성과 분석적 깊이가 우수합니다."
        
    scores['논리 전개의 충분성'] = MetricScore(score=content4_score, description=content4_desc)
    # 7. [조직1] 글의 유기적 구조(서론·본론·결론) (1~5점)
    trans_keywords = ['우선', '첫째', '다음으로', '나아가', '더불어', '하지만', '그러나', '반면', '따라서', '결과적으로', '결론적으로']
    trans_matches = sum(1 for k in trans_keywords if k in text)
    org1_score = 3.0
    if paragraph_count in [4, 5]:
        org1_score += 1.0
    elif paragraph_count < 3:
        org1_score -= 1.5
    org1_score += min(1.0, trans_matches * 0.15)
    org1_score = min(5.0, max(1.0, org1_score))
    org1_desc = "서론-본론-결론의 유기적인 논리적 삼단 구성이 구조적으로 체계적이며, 문단 전환 연결어들이 흐름을 매끄럽게 유도해 줍니다." if org1_score >= 4.0 else "문단 구분이 거의 없거나 하나의 호흡에 여러 중심 생각이 뭉쳐 있습니다. 서론(1)-본론(2~3)-결론(1)의 교과서적 구조로 명확히 분절하고 유기적으로 연결해 주세요."
    scores['글의 유기적 구조(서론·본론·결론)'] = MetricScore(score=round(org1_score, 1), description=org1_desc)
    org1_score = round(org1_score, 1)
    # 요구사항 6 (3단계 세분화)
    if org1_score < 2.5:
        org1_desc = "문단 구분이 전혀 없거나 서론-본론-결론의 삼단 구성이 해체되어 있어 가독성이 매우 떨어집니다. 서론, 본론, 결론의 경계를 명확히 나누고 문맥 흐름을 처음부터 다시 가다듬어야 합니다."
    elif org1_score < 4.0:
        org1_desc = "문단 구분이 모호하거나 하나의 호흡에 여러 중심 생각이 뭉쳐 있습니다. 서론(1)-본론(2~3)-결론(1)의 구조로 분절하고 유기적인 연결어를 활용해 매끄럽게 다듬어 보세요."
    else:
        org1_desc = "서론-본론-결론의 유기적인 논리적 삼단 구성이 구조적으로 체계적이며, 문단 전환 연결어들이 흐름을 매끄럽게 유도해 줍니다."
        
    scores['글의 유기적 구조(서론·본론·결론)'] = MetricScore(score=org1_score, description=org1_desc)
    # 8. [조직2] 문단의 완결성과 통일성 (1~5점)
    p_lengths = [len(p) for p in paragraphs]
    p_length_std = float(np.std(p_lengths)) if len(p_lengths) > 1 else 999.0
    sentences_per_p = sentence_count / paragraph_count if paragraph_count > 0 else 0
    org2_score = 3.0
    if 4.0 <= sentences_per_p <= 7.0:
        org2_score += 1.0
    if p_length_std < 150:
        org2_score += 1.0
    elif p_length_std > 350:
        org2_score -= 1.0
    org2_score = min(5.0, max(1.0, org2_score))
    org2_desc = "각 문단이 소주제문을 중심으로 균형 있게 서술되었으며, 문단 간 길이 비율이 시각적으로도 조화롭게 유지됩니다." if org2_score >= 4.0 else "어떤 문단은 10문장이 넘을 정도로 방대한 반면, 다른 문단은 단 1문장에 그치고 있습니다. 각 문단이 하나의 일관된 개념 단위를 이루도록 내용 분량을 균등하게 조정해야 합니다."
    scores['문단의 완결성과 통일성'] = MetricScore(score=round(org2_score, 1), description=org2_desc)
    org2_score = round(org2_score, 1)
    # 요구사항 6 (3단계 세분화)
    if org2_score < 2.5:
        org2_desc = "특정 문단의 분량이 기형적으로 비대하거나 1문장짜리 극단적 문단이 방치되어 균형이 무너졌습니다. 각 문단이 하나의 완성된 소주제를 다루도록 내용 분량을 대대적으로 재배분해야 합니다."
    elif org2_score < 4.0:
        org2_desc = "어떤 문단은 방대한 반면, 다른 문단은 단 1~2문장에 그치고 있습니다. 각 문단이 일관된 개념 단위를 이룰 수 있도록 문단 간 분량 균형을 조정하는 것을 권장합니다."
    else:
        org2_desc = "각 문단이 소주제문을 중심으로 균형 있게 서술되었으며, 문단 간 길이 비율이 시각적으로도 조화롭게 유지됩니다."
        
    scores['문단의 완결성과 통일성'] = MetricScore(score=org2_score, description=org2_desc)
    # 9. [표현2] 어문 규범 및 장르 관습 준수 (1~5점)
    bad_endings = len(re.findall(r'\b(요|죠)\b[.!?]', text)) + len(re.findall(r'\b(했음|했슴|음)\b[.!?]', text))
    good_endings = len(re.findall(r'\b(다|것이다|한다|하였다|않는다|있다)\b[.!?]', text))
    total_endpoints = bad_endings + good_endings
    ratio = good_endings / total_endpoints if total_endpoints > 0 else 1.0
    
    expr2_score = 4.8
    if ratio < 0.9:
        expr2_score -= (1.0 - ratio) * 5
    if len(highlights) > 10:
        expr2_score -= 1.0
    expr2_score = min(5.0, max(1.0, expr2_score))
    expr2_desc = "논증문의 격식 있는 표준적인 문어체 종결어미(~다.)와 문장 부호를 일관되게 적용하여 글의 장르적 신뢰성을 잘 갖추고 있습니다." if expr2_score >= 4.0 else "대화형 구어체 어미(~요, ~죠)나 공적인 글에 적절치 않은 명사형 축약 종결(~음, ~함)이 식별되었습니다. 학술용 완전한 문장 어미(~다.)로 통일해 주세요."
    scores['어문 규범 및 장르 관습 준수'] = MetricScore(score=round(expr2_score, 1), description=expr2_desc)
    expr2_score = round(expr2_score, 1)
    # 요구사항 6 (3단계 세분화)
    if expr2_score < 2.5:
        expr2_desc = "공적인 글에 어울리지 않는 약식 종결(~음, ~함) 및 일상 구어체 표현이 빈번하게 식별되어 격식성이 크게 저하되었습니다. 전체 문장을 완전한 문어체 어미(~다.)로 철저히 교정해 주세요."
    elif expr2_score < 4.0:
        expr2_desc = "대화형 구어체 어미(~요, ~죠)나 공적인 글에 적절치 않은 명사형 축약 종결(~음, ~함)이 일부 식별되었습니다. 학술용 완전한 문장 어미(~다.)로 통일해 보세요."
    else:
        expr2_desc = "논증문의 격식 있는 표준적인 문어체 종결어미(~다.)와 문장 부호를 일관되게 적용하여 글의 장르적 신뢰성을 잘 갖추고 있습니다."
        
    scores['어문 규범 및 장르 관습 준수'] = MetricScore(score=expr2_score, description=expr2_desc)
    # ------------------------------------------------------------------
    # 종합 계산 및 등급 산출
    # ------------------------------------------------------------------
    total_sum = sum(item.score for item in scores.values())
    total_average = round(total_sum / len(scores), 2)
    
    # [백엔드 정교화] 종합 평균이 B- 이하(3.5 미만)로 낮은 대역일 때 칭찬 미사여구를 자제하고 객관적 보완 가이드로 필터링
    if total_average < 3.5:
        for key, metric in scores.items():
            if metric.score >= 4.0:
                if key == '문장 및 어휘의 자연스러움':
                    scores[key].description = "문장 길이의 편차가 비교적 단조롭지 않은 흐름을 유지하여 기본적인 요건은 충족하고 있으나, 글 전반의 구조적 논증성과 흐름을 보완하기 위해 세부 단어 배치와 표현을 좀 더 다듬는 노력이 수반되어야 합니다."
                elif key == '반론 고려 및 신중한 표현':
                    scores[key].description = "완화 어구의 활용 빈도는 적절하여 지나친 단정을 일부 피하고 있으나, 글 전반의 학술적 깊이와 논증력을 확보하기 위해 본론의 구체적 근거와 연계하여 주장의 신뢰도를 다각도로 보강하시기 바랍니다."
                elif key == '문제 상황 제시 및 정보성':
                    scores[key].description = "서론에서 기본적인 문제의식을 서술하고 있으나, 독자에게 다가가는 객관적 설득력을 한층 더 높이기 위해 문제와 연계된 통계적 실태나 구체적 사회 배경 정보를 더욱 밀도 있게 보강하는 것이 좋습니다."
                elif key == '주장의 명료성과 일관성':
                    scores[key].description = "중심 주장의 외형적 형태는 갖추어 제기되었으나, 서론에서 던진 질문과 본론의 인과 관계 및 결론의 요약이 일관되게 수렴하고 호응하는지 전체적인 흐름의 논지를 재점검할 필요가 있습니다."
                elif key == '논거의 설득력과 적절성':
                    scores[key].description = "주장을 이끌어내는 추론의 방향은 타당하나, 학술문으로서의 신뢰성과 완성도를 위해 이를 명확히 지탱해 줄 전문 연구 조사나 객관적인 통계 데이터를 촘촘하게 인용해 보강해야 합니다."
                elif key == '논리 전개의 충분성':
                    scores[key].description = "본론의 내용 분량은 비교적 채워졌으나, 각 문단 내 하위 논증들이 비약이나 생략 없이 촘촘하게 전개되었는지 문장 간 인과 관계의 충실도를 좀 더 차분하게 다듬을 필요가 있습니다."
                elif key == '글의 유기적 구조(서론·본론·결론)':
                    scores[key].description = "기본적인 삼단 구성의 골격은 성립하고 있으나, 서론에서 본론, 결론으로 전개되는 문단 간의 유기적 매끄러움을 위해 적절한 접속 어휘를 적용하여 논리적 연결 고리를 단정하게 가가듬어야 합니다."
                elif key == '문단의 완결성과 통일성':
                    scores[key].description = "문단별 길이 비율과 소주제 배치는 양호한 흐름을 유지하고 있으나, 각 문단이 하나의 일관된 개념 단위를 긴밀하게 이루도록 세부 설명의 통일성을 조율하는 것을 권장합니다."
                elif key == '어문 규범 및 장르 관습 준수':
                    scores[key].description = "문어체 종결어미와 부호 등의 격식은 비교적 안정적으로 지켜지고 있으나, 공적인 논증문의 정체성을 확고히 지키기 위해 사소하게 발견되는 비격식 구어 표현 및 어법의 불일치를 철저히 정돈해야 합니다."
    if total_average >= 4.5:
        grade = "A+"
    elif total_average >= 4.0:
        grade = "A-"
    elif total_average >= 3.5:
        grade = "B+"
    elif total_average >= 3.0:
        grade = "B-"
    elif total_average >= 2.5:
        grade = "C+"
    else:
        grade = "C-"
    # 3대 영역 평균 점수 계산
    app_con = sum([
        scores['문제 상황 제시 및 정보성'].score,
        scores['주장의 명료성과 일관성'].score,
        scores['논거의 설득력과 적절성'].score,
        scores['논리 전개의 충분성'].score,
        scores['반론 고려 및 신중한 표현'].score
    ]) / 5.0
    
    app_org = sum([
        scores['글의 유기적 구조(서론·본론·결론)'].score,
        scores['문단의 완결성과 통일성'].score
    ]) / 2.0
    
    app_exp = sum([
        scores['문장 및 어휘의 자연스러움'].score,
        scores['어문 규범 및 장르 관습 준수'].score
    ]) / 2.0
    # 강점 영역 판정: 4.0 이상이거나 3대 영역 중 최고점인 영역
    max_score = max(app_con, app_org, app_exp)
    strong_candidates = []
    if app_con >= 4.0 or app_con == max_score:
        strong_candidates.append(("내용", app_con))
    if app_org >= 4.0 or app_org == max_score:
        strong_candidates.append(("조직", app_org))
    if app_exp >= 4.0 or app_exp == max_score:
        strong_candidates.append(("표현", app_exp))
    # 강점 후보 중 가장 높은 점수를 가진 영역을 선택 (동점 시 내용 -> 조직 -> 표현 순)
    strong_candidates.sort(key=lambda x: x[1], reverse=True)
    strong_domain = strong_candidates[0][0]
    strong_score = round(strong_candidates[0][1], 1)
    # 취약 영역 판정: 내용과 조직 중에서 점수가 더 낮은 영역을 지정
    if app_con < app_org:
        weak_domain = "내용"
        weak_score = round(app_con, 1)
    elif app_con > app_org:
        weak_domain = "조직"
        weak_score = round(app_org, 1)
    # 6종 대역 평점 한줄평 (요구사항 2 복구)
    if total_average >= 4.5:
        grade_commentary = "독자적인 학술적 문제의식과 역동적인 삼단 논증 호흡이 깊이 있게 조화된 훌륭한 명문"
    elif total_average >= 4.0:
        grade_commentary = "체계적인 근거 인용과 신중하고 품격 있는 문장 완화를 갖춘 우수한 논증문"
    elif total_average >= 3.5:
        grade_commentary = "기본적인 논리 구조는 잘 갖추어졌으나, 나만의 개성 있는 표현을 조금 더 보완하면 훌륭한 논증문이 될 수 있습니다."
    elif total_average >= 3.0:
        grade_commentary = "전반적인 흐름은 갖추어졌으나, 문장 구조의 다양성과 단어 배치의 활력을 보완하여 글의 입체감을 높이기를 권장합니다."
    elif total_average >= 2.5:
        grade_commentary = "기본 어법과 문맥 연결은 성립하나, 인위적인 번역 표현을 걷어내고 나만의 문체 활력을 더해야 하는 교정 단계입니다."
    else:
        # 동점일 경우 강점 영역과의 중복을 회피하여 약점 지정
        if strong_domain == "내용":
            weak_domain = "조직"
        else:
            weak_domain = "내용"
        weak_score = round(app_con, 1)
        grade_commentary = "글의 유기적 구조와 문장 다양성을 동시 점검하여 주체적인 흐름으로 다시 고쳐 쓰기를 추천합니다."
    strong_messages = {
        "내용": f"내용 영역(주제 의식 및 신중한 완화 표현)에서 깊이 있는 논리 전개(평균 {strong_score}점)가 돋보이나,",
        "조직": f"조직 영역(삼단 구성 및 문단 완결성)에서 체계적이고 안정적인 짜임새(평균 {strong_score}점)가 돋보이나,",
        "표현": f"표현 영역(다채로운 문장 호흡 및 어문 규범)에서 자연스럽고 생동감 있는 문맥 흐름(평균 {strong_score}점)이 우수하나,"
    }
    weak_messages = {
        "내용": f"상대적으로 보완이 필요한 내용 영역(평균 {weak_score}점)의 구체적인 통계/실태 배경 정보를 보강하고 주장을 신중하게 완화한다면 더욱 설득력 높은 명문이 될 수 있습니다.",
        "조직": f"글의 전반적인 짜임새를 높이기 위해 조직 영역(평균 {weak_score}점)의 서론-본론-결론 간 유기적인 흐름과 문단별 내용 균형을 보완해 보기를 권장합니다."
    }
    grade_commentary = f"{strong_messages[strong_domain]} {weak_messages[weak_domain]}"
    return AnalyzeResponse(
        std_sentence_length=round(std_sentence_length, 2),
        word_ttr=round(word_ttr, 3),
        morpheme_ttr=round(morpheme_ttr, 3),
        total_hedge_density=round(total_hedge_density, 2),
        ai_sentence_warning=ai_sentence_warning,
        ai_sentence_feedback=ai_sentence_feedback,
        ai_word_warning=ai_word_warning,
        ai_word_feedback=ai_word_feedback,
        scores=scores,
        total_average=total_average,
        grade=grade,
        grade_commentary=grade_commentary,
        highlights=highlights,
        char_count=char_count,
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        using_konlpy=USING_KONLPY
    )
# ----------------------------------------------------------------------
# static 폴더 마운트 (HTML, CSS, JS 등 모든 정적 자산 서빙)
# ----------------------------------------------------------------------
app.mount("/", StaticFiles(directory=".", html=True), name="static")
# ----------------------------------------------------------------------
# 로컬 테스트 및 uvicorn 실행
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("[SYSTEM] FastAPI 서버를 시작합니다. http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)