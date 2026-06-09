import os
import json
import csv
import sys
# Windows CP949 콘솔 인코딩 에러 방지용 자동 UTF-8 재설정
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass
# 프로젝트 절대 경로를 추가하여 main 모듈을 임포트할 수 있도록 함
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import analyze_essay, AnalyzeRequest
# 1. 절대 경로 설정 (수동 지정 경로 반영)
STUDENT_DIR = r"E:\내 드라이브\student_essays_2024"
# 일반 공백 경로와 non-breaking space(\xa0) 경로를 모두 지원하여 실행 오류 방지
GRADING_DIR_REGULAR = r"E:\다른 컴퓨터\노트북\경상대\대학원\3학기 26-1\AI 문체비교 교수법\글쓰기 채점 자료 말뭉치 2024\NIKL_GRADING WRITING DATA 2024"
GRADING_DIR_NBSP = r"E:\다른 컴퓨터\노트북\경상대\대학원\3학기 26-1\AI 문체비교 교수법\글쓰기 채점 자료 말뭉치 2024\NIKL_GRADING WRITING DATA" + "\xa0" + "2024"
if os.path.exists(GRADING_DIR_NBSP):
    GRADING_DIR = GRADING_DIR_NBSP
else:
    GRADING_DIR = GRADING_DIR_REGULAR
def parse_student_essay_text(file_path):
    """학생 글 파일에서 paragraph만 추출하여 텍스트 본문으로 재구성합니다 (sentence 무시)"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.json':
        with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            data = json.load(f)
        
        # 1. 국립국어원 표준 스키마: document -> paragraph -> form 추출 (sentence 배열 무시)
        text_list = []
        if 'document' in data and isinstance(data['document'], list):
            for doc in data['document']:
                if 'paragraph' in doc and isinstance(doc['paragraph'], list):
                    for p in doc['paragraph']:
                        if isinstance(p, dict) and 'form' in p and isinstance(p['form'], str):
                            text_list.append(p['form'])
        
        # 2. 추출된 단락 텍스트가 존재하면 깨끗하게 양끝 공백을 자르고 줄바꿈(\n)으로 연결
        if text_list:
            return "\n".join(t.strip() for t in text_list if t.strip())
        
        # Fallback: 일반적인 다른 텍스트 키 탐색
        for key in ['text', 'content', 'essay', 'body']:
            if key in data and isinstance(data[key], str):
                return data[key].strip()
        
        # 최후의 수단: 가장 긴 문자열 값 탐색
        longest_str = ""
        for val in data.values():
            if isinstance(val, str) and len(val) > len(longest_str):
                longest_str = val
        return longest_str.strip()
    else:
        # 일반 TXT 파일인 경우
        with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            return f.read().strip()
def main():
    print("==================================================================")
    print("      🚀 대학생 논증문 채점 알고리즘 신뢰도 대대적 검증 (v2)")
    print("==================================================================")
    
    # 디렉토리 존재 여부 확인
    if not os.path.exists(STUDENT_DIR):
        print(f"❌ 학생글 디렉토리를 찾을 수 없습니다: {STUDENT_DIR}")
        sys.exit(1)
    if not os.path.exists(GRADING_DIR):
        print(f"❌ 채점 자료 디렉토리를 찾을 수 없습니다: {GRADING_DIR}")
        sys.exit(1)
        
    # 학생 글 목록 (GWRW 시작하는 .json 또는 .txt)
    all_files = os.listdir(STUDENT_DIR)
    student_files = [f for f in all_files if (f.endswith('.json') or f.endswith('.txt')) and f.startswith('GWRW')]
    student_files.sort()
    
    print(f"✓ 감지된 학생 글 파일 수: {len(student_files)}개")
    
    # 채점 자료 목록 (.json)
    grading_files = [f for f in os.listdir(GRADING_DIR) if f.endswith('.json') and f.startswith('GWGR')]
    grading_files_set = set(grading_files)
    print(f"✓ 감지된 채점 데이터 파일 수: {len(grading_files)}개")
    
    # 1. 미채점 파일 분류 및 목록 생성
    unscored_files = []
    matched_files = [] # (student_filename, grading_filepath)
    
    for f in student_files:
        student_id = os.path.splitext(f)[0]
        # GWRW -> GWGR 로 교체하여 매칭 파일명 확인
        expected_grading_filename = f.replace('GWRW', 'GWGR')
        # 혹시 확장자가 다를 수 있으므로 json으로 고정
        expected_grading_filename = os.path.splitext(expected_grading_filename)[0] + '.json'
        
        grading_filepath = os.path.join(GRADING_DIR, expected_grading_filename)
        
        if expected_grading_filename in grading_files_set and os.path.exists(grading_filepath):
            matched_files.append((f, grading_filepath))
        else:
            unscored_files.append(student_id)
            
    # 미채점 목록 저장
    project_dir = os.path.dirname(os.path.abspath(__file__))
    unscored_list_path = os.path.join(project_dir, '미채점_파일_목록2.txt')
    with open(unscored_list_path, 'w', encoding='utf-8') as uf:
        for item in unscored_files:
            uf.write(item + '\n')
            
    print(f"✓ 미채점 학생 글 분류 완료: {len(unscored_files)}개 (미채점_파일_목록2.txt 저장됨)")
    print(f"✓ 매칭 완료된 채점 글 수: {len(matched_files)}개")
    
    # 2. 매칭 데이터 채점 비교 및 통계 연산
    comparison_csv_path = os.path.join(project_dir, '인간_vs_앱_채점_비교2.csv')
    
    csv_headers = [
        '글 ID', '사람 내용점수', '앱 내용점수', 
        '사람 조직점수', '앱 조직점수', 
        '사람 표현점수', '앱 표현점수', '문장 표현 경직도 진단여부'
    ]
    
    processed_count = 0
    total_con_error = 0.0
    total_org_error = 0.0
    total_exp_error = 0.0
    
    print("\n▶ 점수 교차 비교 연산 진행 중...")
    
    with open(comparison_csv_path, 'w', encoding='utf-8-sig', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(csv_headers)
        
        for idx, (student_filename, grading_filepath) in enumerate(matched_files):
            student_id = os.path.splitext(student_filename)[0]
            student_filepath = os.path.join(STUDENT_DIR, student_filename)
            
            # 본문 텍스트 로드
            try:
                essay_text = parse_student_essay_text(student_filepath)
            except Exception as e:
                print(f"⚠️ 학생글 텍스트 로드 실패 ({student_filename}): {e}")
                continue
                
            if not essay_text or len(essay_text.strip()) < 10:
                print(f"⚠️ 학생글 본문이 비어있거나 너무 짧음 ({student_filename})")
            char_count_no_space = len(essay_text.replace(" ", "").replace("\n", "").replace("\r", ""))
            if not essay_text or char_count_no_space < 30:
                print(f"⚠️ 학생글 본문이 비어있거나 너무 짧음 (공백 제외 30자 미만) ({student_filename})")
                continue
                
            # 사람 채점 점수 로드
            try:
                with open(grading_filepath, 'r', encoding='utf-8-sig', errors='ignore') as gf:
                    gr_data = json.load(gf)
                
                eval_data = gr_data['document'][0]['evaluation']['evaluation_data']
                
                # 영역별 인간 총점 추출
                con1 = eval_data['eva_score_con']['evaluator1_score_total_con']
                con2 = eval_data['eva_score_con']['evaluator2_score_total_con']
                human_con = (con1 + con2) / 10.0  # (con1/5 + con2/5)/2
                
                org1 = eval_data['eva_score_org']['evaluator1_score_total_org']
                org2 = eval_data['eva_score_org']['evaluator2_score_total_org']
                human_org = (org1 + org2) / 4.0   # (org1/2 + org2/2)/2
                
                exp1 = eval_data['eva_score_exp']['evaluator1_score_total_exp']
                exp2 = eval_data['eva_score_exp']['evaluator2_score_total_exp']
                human_exp = (exp1 + exp2) / 4.0   # (exp1/2 + exp2/2)/2
                
            except Exception as e:
                print(f"⚠️ 채점 정보 로드 실패 ({os.path.basename(grading_filepath)}): {e}")
                continue
                
            # 우리 앱 채점 점수 연산
            try:
                response = analyze_essay(AnalyzeRequest(text=essay_text))
                
                # 내용 5대 항목 평균
                app_con = sum([
                    response.scores['문제 상황 제시 및 정보성'].score,
                    response.scores['주장의 명료성과 일관성'].score,
                    response.scores['논거의 설득력과 적절성'].score,
                    response.scores['논리 전개의 충분성'].score,
                    response.scores['반론 고려 및 신중한 표현'].score
                ]) / 5.0
                
                # 조직 2대 항목 평균
                app_org = sum([
                    response.scores['글의 유기적 구조(서론·본론·결론)'].score,
                    response.scores['문단의 완결성과 통일성'].score
                ]) / 2.0
                
                # 표현 2대 항목 평균
                app_exp = sum([
                    response.scores['문장 및 어휘의 자연스러움'].score,
                    response.scores['어문 규범 및 장르 관습 준수'].score
                ]) / 2.0
                
                # 문장 표현 경직도 진단 임계치 (표준편차 <= 4.5 or 어절 TTR >= 0.81)
                is_rigid_style = "Y" if (response.std_sentence_length <= 4.5 or response.word_ttr >= 0.81) else "N"
                
            except Exception as e:
                print(f"⚠️ 앱 채점 연산 실패 ({student_filename}): {e}")
                continue
                
            # 오차 계산
            total_con_error += abs(human_con - app_con)
            total_org_error += abs(human_org - app_org)
            total_exp_error += abs(human_exp - app_exp)
            processed_count += 1
            
            # 행 기록
            writer.writerow([
                student_id,
                round(human_con, 3), round(app_con, 3),
                round(human_org, 3), round(app_org, 3),
                round(human_exp, 3), round(app_exp, 3),
                is_rigid_style
            ])
            
            if (idx + 1) % 50 == 0 or (idx + 1) == len(matched_files):
                print(f"   [진행 상황] {idx+1}/{len(matched_files)} 완료 ({(idx+1)/len(matched_files)*100:.1f}%)")
                
    # 3. MAE 계산 및 출력
    if processed_count > 0:
        mae_con = total_con_error / processed_count
        mae_org = total_org_error / processed_count
        mae_exp = total_exp_error / processed_count
        
        print("\n" + "="*60)
        print("          🎉 알고리즘 검증 및 오차 분석 완료 (MAE) - v2")
        print("="*60)
        print(f" 계량 대상 데이터 개수: {processed_count}개")
        print(f" 결과 리포트 저장 위치: {comparison_csv_path}")
        print("-"*60)
        print(" ┌────────────────────────────────────────────────────────┐")
        print(" │             영역별 평균 절대 오차 (MAE) 통계 요약             │")
        print(" ├───────────────────────┬────────────────────────────────┤")
        print(" │       평가 영역       │              MAE               │")
        print(" ├───────────────────────┼────────────────────────────────┤")
        print(f" │       내용 영역       │             {mae_con:.4f}             │")
        print(f" │       조직 영역       │             {mae_org:.4f}             │")
        print(f" │       표현 영역       │             {mae_exp:.4f}             │")
        print(" └───────────────────────┴────────────────────────────────┘")
        print("="*60 + "\n")
    else:
        print("❌ 정상 처리된 데이터가 없어 MAE를 산출할 수 없습니다.")
if __name__ == "__main__":
    main()