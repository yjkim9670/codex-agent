import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const dir = new URL('.', import.meta.url).pathname;
const wb = Workbook.create();
const names = ['테스트 안내', '숫자와 서식', '병합과 긴 내용', '스크롤 경계'];
const sheets = names.map(n => wb.worksheets.add(n));
function base(s, range) {
  s.showGridLines = false;
  s.getRange(range).format.font = {name:'Arial', size:11, color:'#161616'};
  s.getRange(range).format.rowHeight = 26;
  s.getRange(range).format.verticalAlignment = 'center';
  s.getRange(range).format.columnWidthPx = 160;
}
function header(s, range) {
  s.getRange(range).format.fill = '#243746';
  s.getRange(range).format.font = {name:'Arial', size:11, bold:true, color:'#FFFFFF'};
  s.getRange(range).format.horizontalAlignment = 'center';
}
function title(s, text) {
  s.getRange('A2').values = [[text]];
  s.getRange('A2').format.font = {name:'Arial', size:16, bold:true};
  s.getRange('A2').format.rowHeight = 34;
}

const [guide, fmt, merged, scroll] = sheets;
base(guide,'A1:C16');
guide.getRange('A1:A16').format.columnWidthPx = 220;
guide.getRange('B1:B16').format.columnWidthPx = 265;
guide.getRange('C1:C16').format.columnWidthPx = 650;
title(guide, '엑셀 프리뷰 테스트');
guide.getRange('A4:C14').values = [
 ['항목','확인 위치','기대 결과 / 확인 방법'],
 ['숫자 표시','숫자와 서식!B5:B14','날짜·시간·원화·달러·백분율·음수·0·식별자 표시를 비교'],
 ['글꼴·색·테두리','숫자와 서식!B17:B21','굵게·기울임·글자색·배경색·실선·점선·이중선 확인'],
 ['수식 저장 결과','숫자와 서식!B25:B27','150,000 / 15,000 / 165,000 표시 확인'],
 ['가로 병합','병합과 긴 내용!A4:D4','하나의 연한 파란색 셀, 중앙 정렬'],
 ['세로·사각 병합','병합과 긴 내용!A7:A9, C7:D9','병합 영역 클릭·방향키 이동 시 셀 선택 확인'],
 ['긴 내용·복사','병합과 긴 내용!B12:B15','선택 후 전체 내용 확인, 복사 후 줄바꿈·탭·문자 비교'],
 ['시트 전환','아래 4개 시트 탭','시트 전환 후 내용과 선택 주소 확인'],
 ['스크롤','스크롤 경계!A1:BC260','260행 × 55열. 200행·50열 경계 안팎 마커 확인'],
 ['현재 표시 제한','스크롤 경계!AX200, AY201, BC260','제한으로 경계 밖이 안 보이면 잘림 안내 확인'],
 ['테마·좁은 화면','파일 프리뷰 및 새 창','밝은·어두운 테마에서 글자 대비, 내부 가로·세로 스크롤 확인'],
];
header(guide,'A4:C4');
guide.getRange('A16').values = [['모든 데이터는 테스트용 가상 값입니다.']];

base(fmt,'A1:C28');
fmt.getRange('A1:A28').format.columnWidthPx = 235;
fmt.getRange('B1:B28').format.columnWidthPx = 275;
fmt.getRange('C1:C28').format.columnWidthPx = 480;
title(fmt,'숫자·날짜·원본 서식');
fmt.getRange('A4:C14').values = [
 ['유형','실제 셀','기대 표시'],
 ['날짜',new Date('2026-10-19T00:00:00Z'),'2026-10-19'],
 ['날짜·시간',new Date('2026-10-19T14:35:20Z'),'2026-10-19 14:35:20'],
 ['원화',1234567,'₩1,234,567'],
 ['달러',1234.5,'$1,234.50'],
 ['백분율',0.125,'12.5%'],
 ['천 단위·소수',12345.678,'12,345.68'],
 ['음수',-9876.5,'(9,876.50)'],
 ['숫자 0',0,'0'],
 ['앞자리 0 식별자','001234','001234 (문자열)'],
 ['논리값',true,'TRUE'],
];
header(fmt,'A4:C4');
const formats = ['yyyy-mm-dd','yyyy-mm-dd hh:mm:ss','"₩"#,##0','"$"#,##0.00','0.0%','#,##0.00','#,##0.00;(#,##0.00)','0','@','General'];
formats.forEach((f,i) => fmt.getRange(`B${i+5}`).setNumberFormat(f));
fmt.getRange('A16:C21').values = [
 ['스타일','샘플','기대 모습'],
 ['굵게','Bold 123 한글','굵은 글씨'],
 ['기울임','Italic 123 한글','기울어진 글씨'],
 ['색상','파란 글씨 / 연한 파랑 배경','밝은·어두운 테마에서 대비 확인'],
 ['점선 테두리','점선 외곽','상하좌우 점선'],
 ['이중선','합계 스타일','아래쪽 이중선'],
];
header(fmt,'A16:C16');
fmt.getRange('B17').format.font.bold = true;
fmt.getRange('B18').format.font.italic = true;
fmt.getRange('B19').format.fill = '#D0E2FF';
fmt.getRange('B19').format.font.color = '#0043CE';
fmt.getRange('B19').format.borders = {preset:'outside',style:'thin',color:'#0F62FE'};
fmt.getRange('B20').format.borders = {preset:'outside',style:'dashed',color:'#6929C4'};
fmt.getRange('B21').format.borders = {preset:'doubleBottom',color:'#161616'};
fmt.getRange('A23:C27').values = [
 ['계산 항목','값 / 수식','기대 결과'],
 ['공급가 입력',150000,'150,000'],
 ['공급가 참조',null,'150,000'],
 ['세액 (10%)',null,'15,000'],
 ['합계',null,'165,000'],
];
header(fmt,'A23:C23');
fmt.getRange('B25:B27').formulas = [['=B24'],['=B25*10%'],['=SUM(B25:B26)']];
fmt.getRange('B24:B27').setNumberFormat('#,##0');

base(merged,'A1:D22');
merged.getRange('A1:A22').format.columnWidthPx = 200;
merged.getRange('B1:B22').format.columnWidthPx = 400;
merged.getRange('C1:D22').format.columnWidthPx = 190;
title(merged,'병합·정렬·전체 내용 확인');
merged.mergeCells('A4:D4');
merged.getRange('A4').values = [['가로 병합 A4:D4 — 중앙 정렬']];
merged.getRange('A4:D4').format.fill = '#D0E2FF';
merged.getRange('A4:D4').format.horizontalAlignment = 'center';
merged.getRange('A4:D4').format.rowHeight = 42;
merged.mergeCells('A7:A9');
merged.getRange('A7').values = [['세로 병합 A7:A9']];
merged.getRange('A7:A9').format.fill = '#DEFBE6';
merged.mergeCells('C7:D9');
merged.getRange('C7').values = [['사각 병합 C7:D9\n두 줄 내용']];
merged.getRange('C7:D9').format.fill = '#F6F2FF';
merged.getRange('C7:D9').format.wrapText = true;
merged.getRange('C7:D9').format.horizontalAlignment = 'center';
merged.getRange('B7:B9').values = [['위쪽 정렬'],['가운데 정렬'],['아래쪽 정렬']];
merged.getRange('B7:B9').format.rowHeight = 42;
merged.getRange('B7').format.verticalAlignment = 'top';
merged.getRange('B9').format.verticalAlignment = 'bottom';
merged.getRange('A11:B15').values = [
 ['내용 종류','선택·복사용 샘플'],
 ['긴 한 줄','긴 내용 시작: '+ '한글 English 12345 셀 전체 내용 복사 확인. '.repeat(10)+'끝 MARKER-END'],
 ['여러 줄','첫 번째 줄\n두 번째 줄: 줄바꿈 유지\n세 번째 줄: 끝'],
 ['탭·특수문자','탭앞\t탭뒤 / 따옴표 "test" / & < > / 한글 日本語 😀'],
 ['수식처럼 보이는 텍스트',"'=SUM(A1:A2)"],
];
header(merged,'A11:B11');
merged.getRange('B12').format.wrapText = false;
merged.getRange('B13').format.wrapText = true;
merged.getRange('B13').format.rowHeight = 72;
merged.getRange('B14').format.wrapText = true;
merged.getRange('B14').format.rowHeight = 52;
merged.getRange('A17:B19').values = [['빈 셀과 0','구분 샘플'],['빈 셀',null],['숫자 0',0]];
header(merged,'A17:B17');
merged.getRange('B18').format.fill = '#F4F4F4';
merged.getRange('B19').setNumberFormat('0');

base(scroll,'A1:BC260');
const col = n => { let s=''; while(n) {n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);} return s; };
scroll.getRange('A1:BC260').values = Array.from({length:260},(_,r) => Array.from({length:55},(_,c) => r===0?`${col(c+1)} 열`:c===0?`행 ${r+1}`:`R${r+1}C${c+1}`));
header(scroll,'A1:BC1');
scroll.getRange('A1:A260').format.columnWidthPx = 100;
scroll.freezePanes.freezeRows(1);
for (const [cell,label] of [['AX200','경계 안 AX200'],['AY201','경계 밖 AY201'],['BC260','마지막 BC260']]) {
 scroll.getRange(cell).values = [[label]];
 scroll.getRange(cell).format.fill = '#FFF1F1';
 scroll.getRange(cell).format.font.bold = true;
}
wb.recalculate();
if(fmt.getRange('B27').values[0][0] !== 165000) throw new Error('수식 결과 불일치');
console.log((await wb.inspect({kind:'table',range:"'숫자와 서식'!A23:C27",include:'values,formulas',maxChars:1800,tableMaxRows:5,tableMaxCols:3})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!',options:{useRegex:true,maxResults:10},maxChars:1000})).ndjson);
for (let i=0;i<sheets.length;i++) {
 const p=await wb.render({sheetName:names[i],range:['A1:C16','A1:C28','A1:D20','A1:F12'][i],scale:1,format:'png'});
 await fs.writeFile(`${dir}preview-${i+1}.png`,new Uint8Array(await p.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(`${dir}excel-preview-test.xlsx`);
console.log('Saved excel-preview-test.xlsx (4 sheets)');
