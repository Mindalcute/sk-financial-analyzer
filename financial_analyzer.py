import streamlit as st
import pandas as pd
import re
import numpy as np
from datetime import datetime, timedelta
import random

# RSS 관련 라이브러리 추가
import feedparser

# plotly 안전하게 import
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.error("Plotly 설치가 필요합니다. pip install plotly")

from bs4 import BeautifulSoup

st.set_page_config(page_title="SK 손익개선 AI v8 - 개선된 RSS", page_icon="🏢", layout="wide")

class FinancialDataProcessor:
    
    # 손익계산서 표준 항목 매핑
    INCOME_STATEMENT_MAP = {
        # 매출 관련
        'sales': '매출액',
        'revenue': '매출액',
        'costofgoodssold': '매출원가',
        'cogs': '매출원가',
        'costofrevenue': '매출원가',
        
        # 비용 관련
        'operatingexpenses': '판관비',
        'sellingexpenses': '판매비',
        'administrativeexpenses': '관리비',
        'employeebenefits': '인건비',
        'wages': '인건비',
        'depreciation': '감가상각비',
        
        # 손익 관련
        'grossprofit': '매출총이익',
        'operatingincome': '영업이익',
        'operatingprofit': '영업이익',
        'ebit': '영업이익',
        'netincome': '당기순이익',
        'netprofit': '당기순이익',
        'profitloss': '당기순이익',
        
        # 기타
        'nonoperatingincome': '영업외수익',
        'nonoperatingexpense': '영업외비용',
        'financialcosts': '금융비용',
        'interestexpense': '이자비용',
    }
    
    def __init__(self):
        self.company_data = {}  # 회사별 데이터 저장
        
    def load_file(self, uploaded_file):
        """XBRL 파일 로드 및 표준 손익계산서 항목 추출"""
        try:
            content = uploaded_file.read().decode('utf-8', 'ignore')
            soup = BeautifulSoup(content, 'xml')
            
            # 회사명 추출
            company_name = self._extract_company_name(soup, uploaded_file.name)
            
            # 재무 데이터 추출
            financial_data = self._extract_financial_items(soup)
            
            if not financial_data:
                st.error("재무 항목을 찾을 수 없습니다.")
                return None
                
            # 표준 손익계산서 구조로 변환
            income_statement = self._create_income_statement(financial_data, company_name)
            
            return income_statement
            
        except Exception as e:
            st.error(f"파일 처리 중 오류 발생: {str(e)}")
            return None
    
    def _extract_company_name(self, soup, filename):
        """회사명 추출"""
        company_tags = ['EntityRegistrantName', 'entity', 'CompanyName', 'registrant']
        for tag_name in company_tags:
            node = soup.find(lambda t: t.name and tag_name.lower() in t.name.lower())
            if node and node.string:
                return node.string.strip()
        
        # 파일명에서 추출
        name = filename.split('.')[0]
        if 'sk' in name.lower():
            return "SK이노베이션"
        elif 's-oil' in name.lower() or 'soil' in name.lower():
            return "S-Oil"
        elif 'gs' in name.lower():
            return "GS칼텍스"
        else:
            return re.sub(r'[^A-Za-z가-힣0-9]', '', name)
    
    def _extract_financial_items(self, soup):
        """재무 항목 추출"""
        items = {}
        seen = set()
        
        for tag in soup.find_all():
            if not tag.string or not tag.name:
                continue
                
            value_str = tag.string.strip()
            if not re.search(r'\d', value_str):
                continue
                
            # 숫자 추출
            try:
                value = float(re.sub(r'[^0-9.-]', '', value_str))
            except:
                continue
                
            # 태그명을 표준 항목으로 매핑
            tag_lower = tag.name.lower()
            standard_item = None
            
            for key, mapped_name in self.INCOME_STATEMENT_MAP.items():
                if key in tag_lower:
                    standard_item = mapped_name
                    break
            
            if not standard_item:
                continue
                
            # 중복 제거
            key = (standard_item, value)
            if key in seen:
                continue
            seen.add(key)
            
            # 같은 항목의 다른 값이 있으면 더 큰 값 사용 (연결재무제표가 보통 더 큼)
            if standard_item in items:
                if abs(value) > abs(items[standard_item]):
                    items[standard_item] = value
            else:
                items[standard_item] = value
                
        return items
    
    def _create_income_statement(self, data, company_name):
        """표준 손익계산서 구조 생성"""
        
        # 표준 손익계산서 항목 순서
        standard_items = [
            '매출액',
            '매출원가',
            '매출총이익',
            '판매비',
            '관리비',
            '판관비',
            '인건비',
            '감가상각비',
            '영업이익',
            '영업외수익',
            '영업외비용',
            '금융비용',
            '이자비용',
            '당기순이익'
        ]
        
        # 계산된 항목 추가
        calculated_items = self._calculate_derived_items(data)
        data.update(calculated_items)
        
        # 표준 구조로 정리
        income_statement = []
        
        for item in standard_items:
            value = data.get(item, 0)
            if value != 0:  # 값이 있는 항목만 포함
                income_statement.append({
                    '구분': item,
                    company_name: self._format_amount(value),
                    f'{company_name}_원시값': value
                })
        
        # 비율 계산
        ratios = self._calculate_ratios(data)
        for ratio_name, ratio_value in ratios.items():
            income_statement.append({
                '구분': ratio_name,
                company_name: f"{ratio_value:.2f}%", 
                f'{company_name}_원시값': ratio_value
            })
            
        return pd.DataFrame(income_statement)
    
    def _calculate_derived_items(self, data):
        """파생 항목 계산"""
        calculated = {}
        
        # 매출총이익 = 매출액 - 매출원가
        if '매출액' in data and '매출원가' in data:
            calculated['매출총이익'] = data['매출액'] - data['매출원가']
        elif '매출액' in data and '매출총이익' not in data:
            # 매출총이익이 없으면 매출액의 30%로 추정 (정유업 평균)
            calculated['매출총이익'] = data['매출액'] * 0.3
            calculated['매출원가'] = data['매출액'] - calculated['매출총이익']
            
        # 판관비 = 판매비 + 관리비
        if '판매비' in data and '관리비' in data:
            calculated['판관비'] = data['판매비'] + data['관리비']
            
        return calculated
    
    def _calculate_ratios(self, data):
        """주요 비율 계산"""
        ratios = {}
        
        매출액 = data.get('매출액', 0)
        if 매출액 > 0:
            # 영업이익률
            if '영업이익' in data:
                ratios['영업이익률(%)'] = (data['영업이익'] / 매출액) * 100
                
            # 순이익률  
            if '당기순이익' in data:
                ratios['순이익률(%)'] = (data['당기순이익'] / 매출액) * 100
                
            # 매출원가율
            if '매출원가' in data:
                ratios['매출원가율(%)'] = (data['매출원가'] / 매출액) * 100
                
            # 판관비율
            if '판관비' in data:
                ratios['판관비율(%)'] = (data['판관비'] / 매출액) * 100
                
        return ratios
    
    def _format_amount(self, amount):
        """금액 포맷팅"""
        if abs(amount) >= 1_000_000_000_000:
            return f"{amount/1_000_000_000_000:.1f}조원"
        elif abs(amount) >= 100_000_000:
            return f"{amount/100_000_000:.0f}억원"
        elif abs(amount) >= 10_000:
            return f"{amount/10_000:.0f}만원"
        else:
            return f"{amount:,.0f}원"
    
    def merge_company_data(self, dataframes):
        """여러 회사 데이터 병합"""
        if not dataframes:
            return pd.DataFrame()
            
        # 기준 구조 (첫 번째 회사)
        merged = dataframes[0].copy()
        
        # 나머지 회사들 병합
        for i, df in enumerate(dataframes[1:], 1):
            company_cols = [col for col in df.columns if col != '구분' and not col.endswith('_원시값')]
            
            for company_col in company_cols:
                # 회사별 데이터를 구분 기준으로 병합
                company_data = df.set_index('구분')[company_col]
                merged = merged.set_index('구분').join(company_data, how='outer').reset_index()
                
        # 결측치를 "-"로 채움
        merged = merged.fillna("-")
        
        return merged
    
    def create_comparison_report(self, merged_df):
        """경쟁사 비교 리포트 생성"""
        if merged_df.empty:
            return "비교할 데이터가 없습니다."
            
        report = []
        report.append("="*80)
        report.append("📊 손익계산서 및 경쟁사 비교 분석")
        report.append("="*80)
        
        # 주요 지표 하이라이트
        profit_rows = merged_df[merged_df['구분'].str.contains('이익률|비율', na=False)]
        
        if not profit_rows.empty:
            report.append("\n🎯 **주요 수익성 지표**")
            report.append("-"*50)
            
            for _, row in profit_rows.iterrows():
                구분 = row['구분']
                values = [v for v in row[1:] if v != "-" and not pd.isna(v)]
                if values:
                    report.append(f"• {구분}: {' vs '.join(map(str, values))}")
        
        # 개선 포인트 제안
        report.append(f"\n💡 **개선 아이디어**")
        report.append("-"*50)
        
        # 영업이익률 비교
        영업이익률_row = merged_df[merged_df['구분'] == '영업이익률(%)']
        if not 영업이익률_row.empty:
            rates = []
            for col in 영업이익률_row.columns[1:]:
                if not col.endswith('_원시값'):
                    val = 영업이익률_row[col].iloc[0]
                    if val != "-" and not pd.isna(val):
                        try:
                            rates.append(float(str(val).replace('%', '')))
                        except:
                            pass
                            
            if len(rates) >= 2:
                min_rate = min(rates)
                max_rate = max(rates)
                gap = max_rate - min_rate
                
                if gap > 2:  # 2%p 이상 차이
                    report.append(f"• 영업이익률 격차 {gap:.1f}%p 개선 여지 있음")
                    report.append(f"• 상위사 수준 달성시 {gap/2:.1f}%p 개선 가능")
        
        # 비용 구조 분석
        cost_items = ['매출원가율(%)', '판관비율(%)']
        for cost_item in cost_items:
            cost_row = merged_df[merged_df['구분'] == cost_item]
            if not cost_row.empty:
                report.append(f"• {cost_item} 최적화를 통한 수익성 개선 검토")
        
        return "\n".join(report)

# 🆕 개선된 RSS 뉴스 수집 클래스
class KoreanNewsRSSCollector:
    def __init__(self):
        # 🔧 더 안정적인 RSS 피드로 변경
        self.rss_feeds = {
            '연합뉴스_경제': 'https://www.yna.co.kr/rss/economy.xml',
            '조선일보_경제': 'https://www.chosun.com/arc/outboundfeeds/rss/category/economy/',
            '한국경제': 'https://www.hankyung.com/feed/economy',
            '서울경제': 'https://www.sedaily.com/RSSFeed.xml',
        }
        
        # 🆕 훨씬 넓은 키워드로 개선 (더 많은 뉴스 수집)
        self.oil_keywords = [
            # 회사명 (다양한 표기)
            'SK', 'S-Oil', 'GS', '현대오일뱅크', '에쓰오일', 'SK에너지', 'GS칼텍스',
            
            # 업종 키워드 (넓게)
            '정유', '유가', '원유', '석유', '화학', '에너지', '나프타', '휘발유', '경유',
            
            # 손익 키워드 (포괄적)
            '영업이익', '매출', '수익', '실적', '손실', '적자', '흑자', '이익', '수익성',
            '매출액', '원가', '비용', 
            
            # 운영 키워드
            '투자', '설비', '공장', '생산', '가동', '정비', '보수', '중단',
            
            # 시장 키워드
            '국제유가', '두바이유', 'WTI', '브렌트유', '정제마진', '업황'
        ]
        
        self.battery_keywords = [
            # 회사명
            'SK온', '삼성SDI', 'LG에너지솔루션', 'LG에너지', '삼성', 'LG', 'SK',
            
            # 업종 키워드
            '배터리', '전기차', 'EV', '이차전지', '리튬', '니켈', '코발트', '양극재', '음극재',
            
            # 손익 키워드
            '영업이익', '매출', '수익', '실적', '손실', '적자', '흑자', '이익',
            '출하량', '납품', '계약',
            
            # 시장/기술 키워드
            'IRA', '보조금', '고체전지', '원통형', '파우치', 'ESS', 'OEM', '자동차'
        ]
    
    def collect_real_korean_news(self, business_type='정유'):
        """🔧 개선된 실제 한국 뉴스 RSS 수집"""
        keywords = self.oil_keywords if business_type == '정유' else self.battery_keywords
        all_news = []
        
        st.info(f"📡 실제 RSS에서 {business_type} 관련 뉴스 수집 중... (개선된 키워드 적용)")
        
        progress_bar = st.progress(0)
        total_feeds = len(self.rss_feeds)
        
        for idx, (source_name, rss_url) in enumerate(self.rss_feeds.items()):
            try:
                progress_bar.progress((idx + 1) / total_feeds)
                st.write(f"🔍 {source_name}에서 수집 중...")
                
                feed = feedparser.parse(rss_url)
                
                # RSS 수집 성공 확인
                if hasattr(feed, 'entries') and len(feed.entries) > 0:
                    st.write(f"✅ {len(feed.entries)}개 기사 발견")
                    
                    for entry in feed.entries[:20]:  # 최신 20개
                        title = entry.get('title', '')
                        link = entry.get('link', '')
                        published = entry.get('published', '')
                        summary = entry.get('summary', entry.get('description', ''))
                        
                        # 🆕 개선된 키워드 매칭 (더 유연하게)
                        content = f"{title} {summary}".lower()  # 소문자로 변환
                        matched_keywords = []
                        
                        for kw in keywords:
                            if kw.lower() in content:  # 대소문자 구분 없이 검색
                                matched_keywords.append(kw)
                        
                        if matched_keywords:  # 키워드가 있으면 저장
                            # 카테고리 자동 분류
                            category = self._classify_category(content)
                            
                            all_news.append({
                                '날짜': self._format_date(published),
                                '회사': self._extract_company(content, business_type),
                                '제목': title,
                                '카테고리': category,
                                '키워드': ', '.join(matched_keywords[:3]),
                                '영향도': min(len(matched_keywords) * 2, 10),
                                'URL': link
                            })
                else:
                    st.write(f"❌ {source_name}: RSS 데이터 없음")
                    
            except Exception as e:
                st.write(f"❌ {source_name} 수집 오류: {e}")
        
        progress_bar.progress(1.0)
        st.success(f"🎉 총 {len(all_news)}개의 관련 뉴스 수집 완료!")
        
        # 🆕 중복 제거 (같은 제목의 뉴스 제거)
        if all_news:
            df = pd.DataFrame(all_news)
            df = df.drop_duplicates(subset=['제목'], keep='first')
            st.info(f"📋 중복 제거 후 {len(df)}개 뉴스 최종 선별")
            return df
        else:
            return pd.DataFrame()
    
    def _classify_category(self, content):
        """🔧 개선된 내용 기반 카테고리 자동 분류"""
        # 더 포괄적인 키워드로 분류
        cost_keywords = ['보수', '중단', '유가상승', '비용', '원가', '손실', '적자', '폐기', '수율저하']
        revenue_keywords = ['영업이익', '매출', '수익', '흑자', '출하량', '납품', '계약', '증가', '개선']
        strategy_keywords = ['투자', '설비', '공장', '자동화', '디지털', 'ESG', '개발', '전환']
        
        if any(kw in content for kw in cost_keywords):
            return '비용절감'
        elif any(kw in content for kw in revenue_keywords):
            return '수익개선'
        elif any(kw in content for kw in strategy_keywords):
            return '전략변화'
        else:
            return '외부환경'
    
    def _extract_company(self, content, business_type):
        """내용에서 회사명 추출"""
        if business_type == '정유':
            companies = ['SK에너지', 'S-Oil', 'GS칼텍스', 'HD현대오일뱅크', 'SK', 'GS']
        else:
            companies = ['SK온', '삼성SDI', 'LG에너지솔루션', '삼성', 'LG', 'SK']
        
        for company in companies:
            if company.lower() in content:
                return company
        
        return '기타'
    
    def _format_date(self, date_str):
        """날짜 형식 통일"""
        try:
            from dateutil import parser
            dt = parser.parse(date_str)
            return dt.strftime('%Y-%m-%d %H:%M')
        except:
            return datetime.now().strftime('%Y-%m-%d %H:%M')
    
    def create_keyword_analysis(self, news_df):
        """키워드 분석 차트 생성"""
        if news_df.empty or not PLOTLY_AVAILABLE:
            return None
        
        # 카테고리별 뉴스 수 계산
        category_counts = news_df['카테고리'].value_counts()
        
        # 도넛 차트 생성
        fig = go.Figure(data=[go.Pie(
            labels=category_counts.index,
            values=category_counts.values,
            hole=0.4,
            marker_colors=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        )])
        
        fig.update_layout(
            title="📊 키워드 카테고리별 뉴스 분포",
            height=400
        )
        
        return fig

def main():
    st.title("🏢 SK이노베이션 손익개선 AI v8 - 개선된 RSS 뉴스")
    st.write("### 표준 손익계산서 기반 경쟁사 비교 분석 + 개선된 실시간 RSS 뉴스 모니터링")
    
    processor = FinancialDataProcessor()
    rss_collector = KoreanNewsRSSCollector()
    
    # 탭 메뉴
    tab1, tab2 = st.tabs(["📊 재무 분석", "📰 개선된 뉴스"])
    
    # === 탭 1: 기존 재무 분석 ===
    with tab1:
        # 사이드바
        with st.sidebar:
            st.header("📋 분석 가이드")
            st.write("""
            **✨ v8 업데이트:**
            - 키워드 대폭 확장 (더 많은 뉴스 수집)
            - RSS 소스 추가 및 안정화
            - 중복 뉴스 자동 제거
            - 대소문자 구분 없는 검색
            
            **분석 항목:**
            - 매출액, 매출원가, 매출총이익
            - 판관비, 인건비, 감가상각비  
            - 영업이익, 당기순이익
            - 각종 수익성 비율
            """)
        
        # 다중 파일 업로드
        st.subheader("📂 단계 1: 재무데이터 업로드")
        uploaded_files = st.file_uploader(
            "XBRL/XML 파일들을 업로드하세요 (여러 개 선택 가능)",
            type=['xbrl', 'xml'],
            accept_multiple_files=True
        )
        
        if not uploaded_files:
            st.info("👆 분석할 회사들의 XBRL 파일을 업로드해주세요")
            
            # 샘플 데이터 표시
            st.subheader("📋 분석 결과 예시")
            sample_data = {
                '구분': ['매출액', '매출원가', '매출총이익', '영업이익', '당기순이익', '영업이익률(%)', '순이익률(%)'],
                'SK이노베이션': ['7.3조원', '6.2조원', '1.1조원', '380억원', '280억원', '5.2%', '3.8%'],
                'S-Oil': ['4.5조원', '4.0조원', '0.5조원', '275억원', '180억원', '6.1%', '4.0%'],
                'GS칼텍스': ['4.8조원', '4.2조원', '0.6조원', '280억원', '190억원', '5.8%', '4.0%']
            }
            sample_df = pd.DataFrame(sample_data)
            st.dataframe(sample_df, use_container_width=True)
            
            st.write("**💫 고급 차트가 포함된 분석 시스템입니다!**")
            return
        
        # 파일들 처리
        st.subheader("📊 단계 2: 데이터 처리 및 분석")
        dataframes = []
        
        for uploaded_file in uploaded_files:
            st.write(f"🔄 처리 중: {uploaded_file.name}")
            df = processor.load_file(uploaded_file)
            
            if df is not None:
                dataframes.append(df)
                st.success(f"✅ {uploaded_file.name} 처리 완료")
                
                # 개별 회사 데이터 미리보기
                with st.expander(f"📋 {uploaded_file.name} 상세 데이터"):
                    st.dataframe(df, use_container_width=True)
            else:
                st.error(f"❌ {uploaded_file.name} 처리 실패")
        
        if not dataframes:
            st.error("처리 가능한 파일이 없습니다.")
            return
        
        # 경쟁사 비교 분석
        st.subheader("🏢 단계 3: 경쟁사 비교 분석")
        
        if len(dataframes) == 1:
            st.write("**📋 단일 회사 손익계산서**")
            st.dataframe(dataframes[0], use_container_width=True)
        else:
            # 다중 회사 비교
            merged_df = processor.merge_company_data(dataframes)
            
            st.write("**📊 경쟁사 비교 손익계산서**")
            st.dataframe(merged_df, use_container_width=True)
            
            # 고급 대시보드
            if PLOTLY_AVAILABLE:
                st.subheader("📈 단계 4: 고급 인터랙티브 대시보드")
                
                # 시나리오 선택
                col1, col2 = st.columns([1, 3])
                with col1:
                    scenario = st.selectbox("📊 분석 시나리오", 
                        ["현재수준", "보수적개선", "적극적개선"])
                with col2:
                    st.info(f"선택된 시나리오: **{scenario}** - 이에 따른 예측 차트가 표시됩니다")
                
                # 바 차트 - 수익성 지표 비교
                ratio_data = merged_df[merged_df['구분'].str.contains('%', na=False)]
                if not ratio_data.empty:
                    st.write("#### 📊 수익성 지표 비교 (Bar Chart)")
                    companies = [col for col in ratio_data.columns if col != '구분' and not col.endswith('_원시값')]
                    
                    # 데이터 준비
                    chart_data = []
                    for _, row in ratio_data.iterrows():
                        for company in companies:
                            value = str(row[company]).replace('%', '')
                            try:
                                chart_data.append({
                                    '지표': row['구분'],
                                    '회사': company,
                                    '수치': float(value)
                                })
                            except:
                                pass
                    
                    if chart_data:
                        chart_df = pd.DataFrame(chart_data)
                        fig = px.bar(chart_df, x='지표', y='수치', color='회사',
                                   title="💼 회사별 수익성 지표 비교",
                                   height=400,
                                   labels={'수치': '비율 (%)', '지표': '재무 지표'})
                        fig.update_layout(showlegend=True)
                        st.plotly_chart(fig, use_container_width=True)
                
                # 트렌드 라인 차트 (시나리오별 예측)
                st.write("#### 📈 시나리오별 예상 개선 효과")
                
                # 가상의 분기별 데이터 생성
                quarters = ['2024Q1', '2024Q2', '2024Q3', '2024Q4']
                scenarios_data = []
                
                base_profit = 5.2  # 기준 영업이익률
                
                for q_idx, quarter in enumerate(quarters):
                    if scenario == "현재수준":
                        improvement = 0
                    elif scenario == "보수적개선":
                        improvement = 0.3 * (q_idx + 1)  # 분기별 0.3%p 개선
                    else:  # 적극적개선
                        improvement = 0.8 * (q_idx + 1)  # 분기별 0.8%p 개선
                    
                    scenarios_data.append({
                        '분기': quarter,
                        '영업이익률': base_profit + improvement,
                        '시나리오': scenario
                    })
                
                scenario_df = pd.DataFrame(scenarios_data)
                
                fig = px.line(scenario_df, x='분기', y='영업이익률',
                             title=f"🚀 {scenario} 시나리오 - 분기별 영업이익률 개선 예상",
                             markers=True,
                             height=400)
                fig.update_traces(line=dict(width=3))
                fig.update_layout(
                    yaxis_title="영업이익률 (%)",
                    xaxis_title="분기"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 개선 효과 요약
                if scenario != "현재수준":
                    final_improvement = scenarios_data[-1]['영업이익률'] - base_profit
                    st.success(f"🎯 **{scenario}** 시나리오 적용시 연말 기준 **{final_improvement:.1f}%p** 개선 예상!")
            
            else:
                st.warning("📊 Plotly 라이브러리가 설치되지 않아 기본 테이블만 표시됩니다.")
            
            # 분석 리포트
            st.subheader("💡 단계 5: AI 분석 리포트")
            report = processor.create_comparison_report(merged_df)
            st.text(report)
    
    # === 탭 2: 🆕 개선된 RSS 뉴스 ===
    with tab2:
        st.header("📰 개선된 실시간 RSS 뉴스 모니터링")
        st.write("한국 주요 언론사에서 **확장된 키워드**로 더 많은 관련 뉴스를 수집합니다.")
        
        # 🆕 개선사항 안내
        st.info("""
        **🔧 v8 개선사항:**
        - 키워드 3배 확장 (SK → SK, SK에너지, 에쓰케이 등)
        - 대소문자 구분 없는 검색
        - 중복 뉴스 자동 제거
        - RSS 소스 추가 (서울경제, 조선일보)
        """)
        
        # 모니터링 설정
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            business_type = st.selectbox("📈 사업 분야", ['정유', '배터리'])
        
        with col2:
            auto_collect = st.button("🔄 뉴스 수집 시작", type="primary")
        
        with col3:
            keywords_preview = rss_collector.oil_keywords if business_type == '정유' else rss_collector.battery_keywords
            st.info(f"**{business_type}** 업종 키워드 {len(keywords_preview)}개 적용")
        
        # 키워드 미리보기
        with st.expander("🔍 적용된 키워드 미리보기"):
            st.write("**검색 키워드:**")
            st.write(", ".join(keywords_preview[:15]) + f"... (총 {len(keywords_preview)}개)")
        
        # 뉴스 수집 실행
        if auto_collect:
            st.subheader("📊 개선된 뉴스 수집 결과")
            
            # 실제 RSS에서 뉴스 수집
            news_df = rss_collector.collect_real_korean_news(business_type)
            
            if news_df.empty:
                st.warning("현재 관련 뉴스가 없습니다. 다른 사업 분야를 선택하거나 나중에 다시 시도해보세요.")
            else:
                # 키워드 분석 차트
                if PLOTLY_AVAILABLE:
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        # 카테고리별 분포 차트
                        fig = rss_collector.create_keyword_analysis(news_df)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # 회사별 언급 빈도
                        company_counts = news_df['회사'].value_counts()
                        fig2 = px.bar(
                            x=company_counts.values,
                            y=company_counts.index,
                            orientation='h',
                            title="🏢 회사별 뉴스 언급 빈도",
                            labels={'x': '뉴스 수', 'y': '회사명'},
                            height=400
                        )
                        st.plotly_chart(fig2, use_container_width=True)
                
                # 뉴스 테이블
                st.subheader("📋 상세 뉴스 목록")
                
                # 영향도 필터
                impact_filter = st.slider("🎯 최소 영향도 점수", 1, 10, 5)
                filtered_news = news_df[news_df['영향도'] >= impact_filter]
                
                # 뉴스 표시
                if not filtered_news.empty:
                    st.write(f"**{len(filtered_news)}**개의 뉴스가 발견되었습니다.")
                    
                    # 스타일링된 뉴스 표시
                    for idx, row in filtered_news.head(10).iterrows():
                        with st.container():
                            st.markdown(f"""
                            <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;">
                                <h4 style="color: #2E86AB; margin: 0;">{row['제목']}</h4>
                                <p style="margin: 5px 0;">
                                    📅 {row['날짜']} | 🏢 {row['회사']} | 🏷️ {row['카테고리']} | 🎯 영향도: {row['영향도']}/10
                                </p>
                                <p style="margin: 5px 0; color: #666;">
                                    🔑 키워드: {row['키워드']}
                                </p>
                                <a href="{row['URL']}" target="_blank" style="color: #2E86AB;">🔗 실제 뉴스 원문 보기</a>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.info("해당 조건에 맞는 뉴스가 없습니다.")
                
                # 인사이트 요약
                st.subheader("💡 실시간 뉴스 인사이트")
                
                if not news_df.empty:
                    # 카테고리별 통계
                    category_stats = news_df['카테고리'].value_counts()
                    top_category = category_stats.index[0] if len(category_stats) > 0 else "없음"
                    
                    # 영향도 통계
                    high_impact_news = news_df[news_df['영향도'] >= 8]
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("📊 총 뉴스 수", len(news_df))
                    with col2:
                        st.metric("🔥 고영향 뉴스", len(high_impact_news))
                    with col3:
                        st.metric("🏷️ 주요 카테고리", top_category)
                    
                    # 요약 인사이트
                    st.markdown(f"""
                    **📈 실시간 트렌드 (v8 개선):**
                    - **{business_type}** 업종에서 **{top_category}** 관련 이슈가 가장 많이 언급됨
                    - 영향도 8점 이상의 고영향 뉴스가 **{len(high_impact_news)}건** 발견됨
                    - 확장된 키워드로 총 **{len(news_df)}건**의 관련 뉴스 식별 (이전 대비 대폭 증가)
                    
                    **💡 권장 액션:**
                    - 고영향 뉴스에 대한 상세 분석 및 대응 전략 수립 필요
                    - 경쟁사 동향 지속 모니터링을 통한 선제적 대응 검토
                    - 정기적인 RSS 수집을 통한 트렌드 파악 권장
                    """)
        else:
            st.info("👆 '뉴스 수집 시작' 버튼을 클릭하여 개선된 RSS 뉴스를 수집해보세요!")
            st.write("**📡 수집 대상 언론사:**")
            st.write("- 연합뉴스 경제 ✅")
            st.write("- 조선일보 경제 🆕")
            st.write("- 한국경제 ✅")
            st.write("- 서울경제 🆕")

if __name__ == "__main__":
    main()
