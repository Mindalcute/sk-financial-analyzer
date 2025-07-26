import streamlit as st
import pandas as pd
import re
import numpy as np

st.set_page_config(page_title="SK 손익개선 AI v3", page_icon="🏢", layout="wide")

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
            from bs4 import BeautifulSoup
        except ImportError:
            st.error("pip install beautifulsoup4 lxml 필요")
            return None
            
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
                    if val != "-":
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

def main():
    st.title("🏢 SK이노베이션 손익개선 AI v3 - 세밀한 경쟁분석")
    st.write("### 표준 손익계산서 기반 경쟁사 비교 분석")
    
    processor = FinancialDataProcessor()
    
    # 사이드바
    with st.sidebar:
        st.header("📋 분석 가이드")
        st.write("""
        **새로운 기능:**
        - 표준 손익계산서 구조
        - 다중 회사 비교 분석
        - 자동 비율 계산
        - 개선 아이디어 제안
        
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
        
        st.write("**💡 이런 식으로 표준 손익계산서 구조로 경쟁사를 비교분석합니다!**")
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
        
        # 시각화
        ratio_rows = merged_df[merged_df['구분'].str.contains('%', na=False)]
        if not ratio_rows.empty:
            st.write("**📈 수익성 지표 비교**")
            
            # 차트 데이터 준비
            chart_data = {}
            for _, row in ratio_rows.iterrows():
                metric = row['구분']
                for col in row.index[1:]:
                    if not col.endswith('_원시값') and row[col] != "-":
                        try:
                            value = float(str(row[col]).replace('%', ''))
                            if col not in chart_data:
                                chart_data[col] = {}
                            chart_data[col][metric] = value
                        except:
                            pass
            
            if chart_data:
                chart_df = pd.DataFrame(chart_data).T
                st.bar_chart(chart_df)
        
        # 분석 리포트
        st.subheader("💡 단계 4: AI 분석 리포트")
        report = processor.create_comparison_report(merged_df)
        st.text(report)

if __name__ == "__main__":
    main()
