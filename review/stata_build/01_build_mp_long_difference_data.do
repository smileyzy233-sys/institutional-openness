*------------------------------------------------------------------------------
* File:     explorations/io_mp_longdiff_data/dofiles/01_build_mp_long_difference_data.do
* Project:  制度型开放2000—2019年MP差分数据
* Author:   Codex
* Purpose:  构造MP方程的OLS宽表与PPML两期长表
* Inputs:   data/raw/io/gravity_resolved_fractional_20260914/mp_y_x_cons_2000.dta
*           data/raw/io/gravity_resolved_fractional_20260914/mp_y_x_cons_2019.dta
* Outputs:  data/derived/io_mp_longdiff_data/mp_longdiff_ols.dta
*           data/derived/io_mp_longdiff_data/mp_twoperiod_ppml.dta
*           explorations/io_mp_longdiff_data/output/tables/
* Log:      explorations/io_mp_longdiff_data/logs/01_build_mp_long_difference_data.log
*------------------------------------------------------------------------------
version 15
clear all
set more off
set varabbrev off
capture log close
capture mkdir "data/derived/io_mp_longdiff_data"
capture mkdir "explorations/io_mp_longdiff_data/logs"
capture mkdir "explorations/io_mp_longdiff_data/output"
capture mkdir "explorations/io_mp_longdiff_data/output/tables"
capture mkdir "explorations/io_mp_longdiff_data/output/figures"
log using ///
    "explorations/io_mp_longdiff_data/logs/01_build_mp_long_difference_data.log", ///
    replace text

display "RUN_AUDIT stata_version=" c(stata_version) " stata_flavor=" c(flavor)

*--- 1. 读取两期不可变快照并验证键 -----------------------------------------
use "data/raw/io/gravity_resolved_fractional_20260914/mp_y_x_cons_2000.dta", clear
assert year == 2000
display "SOURCE_2000_ROWS=" _N
confirm numeric variable year sector_amne value raw_mp_score ///
    trade_agreement_dummy idealpoint_abs_distance

append using "data/raw/io/gravity_resolved_fractional_20260914/mp_y_x_cons_2019.dta"
display "SOURCE_APPENDED_ROWS=" _N
assert inlist(year, 2000, 2019)
isid year iso_o iso_d sector_amne
duplicates report year iso_o iso_d sector_amne
display "SOURCE_UNIQUE_KEY_CHECK=PASSED"

count if inrange(sector_amne, 1, 20)
display "ROWS_IN_MP_SECTORS_1_20=" r(N)
keep if inrange(sector_amne, 1, 20)
isid year iso_o iso_d sector_amne

assert value >= 0 & !missing(value)
assert !missing(raw_mp_score)

* 白名单只保留识别字段、解释变量和用户指定的两个控制变量。
keep year iso_o iso_d country_o country_d sector_amne value raw_mp_score ///
    trade_agreement_dummy idealpoint_abs_distance
display "MP_OUTPUT_WHITELIST_APPLIED=PASSED"

egen int origin_id = group(iso_o)
egen int destination_id = group(iso_d)
egen long pair_id = group(iso_o iso_d)
generate byte post_2019 = year == 2019

label variable origin_id "来源国ID"
label variable destination_id "目的国ID"
label variable pair_id "有向国家对ID"
label variable post_2019 "2019年指示变量"

sort pair_id sector_amne year
isid pair_id sector_amne year

* OLS与PPML共同排除本国对及任一端为ROW的国家对。
* 只在临时变量中规范化大小写和首尾Unicode空白；原始ISO字段保持不变。
* 空字符串（包括全为空白）不构成本国对，两个删除条件重叠时只删除一次。
tempvar iso_o_normalized iso_d_normalized domestic_pair row_pair drop_pair
generate strL `iso_o_normalized' = lower(ustrtrim(iso_o))
generate strL `iso_d_normalized' = lower(ustrtrim(iso_d))
generate byte `domestic_pair' = !missing(`iso_o_normalized', `iso_d_normalized') & ///
    `iso_o_normalized' != "" & `iso_d_normalized' != "" & ///
    `iso_o_normalized' == `iso_d_normalized'
generate byte `row_pair' = `iso_o_normalized' == "row" | ///
    `iso_d_normalized' == "row"
generate byte `drop_pair' = `domestic_pair' | `row_pair'

local country_pair_rows_before = _N
count if `domestic_pair'
local domestic_pair_rows = r(N)
count if `row_pair'
local row_pair_rows = r(N)
count if `domestic_pair' & `row_pair'
local overlap_pair_rows = r(N)
count if `drop_pair'
local union_drop_rows = r(N)
display "COUNTRY_PAIR_ROWS_BEFORE=" `country_pair_rows_before'
display "SELF_PAIR_ROWS_FLAGGED=" `domestic_pair_rows'
display "ROW_PAIR_ROWS_FLAGGED=" `row_pair_rows'
display "SELF_ROW_OVERLAP_ROWS=" `overlap_pair_rows'
display "COUNTRY_PAIR_ROWS_DROPPED_UNION=" `union_drop_rows'
if `union_drop_rows' == 0 {
    display "COUNTRY_PAIR_FILTER=检查通过，无需删除"
}
else {
    drop if `drop_pair'
}
display "COUNTRY_PAIR_ROWS_AFTER=" _N
display "COUNTRY_PAIR_ROWS_DROPPED_ACTUAL=" `country_pair_rows_before' - _N
assert `domestic_pair' == 0
assert `row_pair' == 0
isid pair_id sector_amne year
display "COUNTRY_PAIR_FILTER=PASSED"
drop `iso_o_normalized' `iso_d_normalized' `domestic_pair' `row_pair' `drop_pair'

tempfile ppml_panel audit_table inventory_table
save `ppml_panel', replace

*--- 2. 保存PPML两期长表：因变量保留原始非负value --------------------------
use `ppml_panel', clear
order pair_id origin_id destination_id iso_o iso_d country_o country_d ///
    sector_amne year post_2019 value raw_mp_score trade_agreement_dummy ///
    idealpoint_abs_distance
compress
isid pair_id sector_amne year
assert value >= 0 & !missing(value)
save "data/derived/io_mp_longdiff_data/mp_twoperiod_ppml.dta", replace
display "PPML_PANEL_ROWS=" _N
count if value == 0
display "PPML_PANEL_ZERO_VALUE_ROWS=" r(N)
display "PPML_PANEL_SAVED=1"

*--- 3. 构造OLS显式长差分宽表 ---------------------------------------------
use `ppml_panel', clear
drop post_2019
generate byte record_present = 1
reshape wide record_present value raw_mp_score trade_agreement_dummy ///
    idealpoint_abs_distance, ///
    i(pair_id origin_id destination_id iso_o iso_d country_o country_d ///
        sector_amne) ///
    j(year)

rename (record_present2000 record_present2019) ///
    (record_present_2000 record_present_2019)
rename (value2000 value2019) (value_2000 value_2019)
rename (raw_mp_score2000 raw_mp_score2019) ///
    (raw_mp_score_2000 raw_mp_score_2019)
rename (trade_agreement_dummy2000 trade_agreement_dummy2019) ///
    (trade_agreement_dummy_2000 trade_agreement_dummy_2019)
rename (idealpoint_abs_distance2000 idealpoint_abs_distance2019) ///
    (idealpoint_abs_distance_2000 idealpoint_abs_distance_2019)

replace record_present_2000 = 0 if missing(record_present_2000)
replace record_present_2019 = 0 if missing(record_present_2019)
generate byte pair_complete = ///
    record_present_2000 == 1 & record_present_2019 == 1
assert pair_complete == 1

generate byte both_positive = value_2000 > 0 & value_2019 > 0 ///
    if pair_complete == 1 & !missing(value_2000, value_2019)
generate double d_ln_value = ln(value_2019) - ln(value_2000) ///
    if both_positive == 1
generate double d_raw_mp_score = ///
    raw_mp_score_2019 - raw_mp_score_2000 if pair_complete == 1
generate double d_trade_agreement_dummy = ///
    trade_agreement_dummy_2019 - trade_agreement_dummy_2000 ///
    if pair_complete == 1
generate double d_idealpoint_abs_distance = ///
    idealpoint_abs_distance_2019 - idealpoint_abs_distance_2000 ///
    if pair_complete == 1

assert missing(d_ln_value) if both_positive != 1
assert reldif(d_ln_value, ln(value_2019) - ln(value_2000)) < 1e-12 ///
    if !missing(d_ln_value)
assert reldif(d_raw_mp_score, raw_mp_score_2019 - raw_mp_score_2000) < 1e-12 ///
    if !missing(d_raw_mp_score)
assert reldif(d_trade_agreement_dummy, ///
    trade_agreement_dummy_2019 - trade_agreement_dummy_2000) < 1e-12 ///
    if !missing(d_trade_agreement_dummy)
assert reldif(d_idealpoint_abs_distance, ///
    idealpoint_abs_distance_2019 - idealpoint_abs_distance_2000) < 1e-12 ///
    if !missing(d_idealpoint_abs_distance)

label variable pair_complete "2000和2019记录均存在"
label variable both_positive "两年value均严格为正"
label variable d_ln_value "ln(value_2019)-ln(value_2000)"
label variable d_raw_mp_score "MP制度型开放得分差分：2019-2000"
label variable d_trade_agreement_dummy "贸易协定虚拟变量差分：2019-2000"
label variable d_idealpoint_abs_distance "政治距离差分：2019-2000"

order pair_id origin_id destination_id iso_o iso_d country_o country_d ///
    sector_amne pair_complete both_positive value_2000 value_2019 d_ln_value ///
    raw_mp_score_2000 raw_mp_score_2019 d_raw_mp_score ///
    trade_agreement_dummy_2000 trade_agreement_dummy_2019 ///
    d_trade_agreement_dummy idealpoint_abs_distance_2000 ///
    idealpoint_abs_distance_2019 d_idealpoint_abs_distance ///
    record_present_2000 record_present_2019

compress
sort pair_id sector_amne
isid pair_id sector_amne
save "data/derived/io_mp_longdiff_data/mp_longdiff_ols.dta", replace
display "OLS_LONGDIFF_ROWS=" _N
count if both_positive == 1
display "OLS_BOTH_POSITIVE_ROWS=" r(N)
count if !missing(d_trade_agreement_dummy)
display "OLS_VALID_D_TRADE_AGREEMENT_ROWS=" r(N)
count if !missing(d_idealpoint_abs_distance)
display "OLS_VALID_D_POLITICAL_DISTANCE_ROWS=" r(N)
display "OLS_LONGDIFF_SAVED=1"

*--- 4. 输出构建审计表 ------------------------------------------------------
tempname audit_post
postfile `audit_post' str40 metric double value using `audit_table', replace
count
post `audit_post' ("ols_pair_sector_rows") (r(N))
count if both_positive == 1
post `audit_post' ("ols_both_positive_rows") (r(N))
count if missing(d_ln_value)
post `audit_post' ("ols_missing_d_ln_value_rows") (r(N))
count if !missing(d_trade_agreement_dummy)
post `audit_post' ("ols_valid_d_trade_agreement_rows") (r(N))
count if !missing(d_idealpoint_abs_distance)
post `audit_post' ("ols_valid_d_political_distance_rows") (r(N))

use "data/derived/io_mp_longdiff_data/mp_twoperiod_ppml.dta", clear
count
post `audit_post' ("ppml_panel_rows") (r(N))
count if value == 0
post `audit_post' ("ppml_zero_value_rows") (r(N))
count if value > 0
post `audit_post' ("ppml_positive_value_rows") (r(N))
count if missing(trade_agreement_dummy)
post `audit_post' ("ppml_missing_trade_agreement_rows") (r(N))
count if missing(idealpoint_abs_distance)
post `audit_post' ("ppml_missing_political_distance_rows") (r(N))
postclose `audit_post'

use `audit_table', clear
sort metric
export delimited using ///
    "explorations/io_mp_longdiff_data/output/tables/mp_longdiff_build_audit.csv", ///
    replace
list, noobs abbreviate(40)

*--- 5. 输出字段清单并执行最终验证 -----------------------------------------
tempname inventory_post
postfile `inventory_post' str24 dataset str32 variable str16 storage_type ///
    str80 variable_label using `inventory_table', replace

foreach dataset in mp_longdiff_ols mp_twoperiod_ppml {
    use "data/derived/io_mp_longdiff_data/`dataset'.dta", clear
    unab all_variables : _all
    foreach variable of local all_variables {
        local storage_type : type `variable'
        local variable_label : variable label `variable'
        post `inventory_post' ("`dataset'") ("`variable'") ///
            ("`storage_type'") (`"`variable_label'"')
    }
}
postclose `inventory_post'

use `inventory_table', clear
sort dataset variable
export delimited using ///
    "explorations/io_mp_longdiff_data/output/tables/mp_longdiff_variable_inventory.csv", ///
    replace

use "data/derived/io_mp_longdiff_data/mp_longdiff_ols.dta", clear
isid pair_id sector_amne
assert pair_complete == 1
assert missing(d_ln_value) if both_positive != 1
confirm variable d_raw_mp_score d_trade_agreement_dummy ///
    d_idealpoint_abs_distance

use "data/derived/io_mp_longdiff_data/mp_twoperiod_ppml.dta", clear
isid pair_id sector_amne year
assert inlist(year, 2000, 2019)
assert value >= 0 & !missing(value)
confirm variable raw_mp_score trade_agreement_dummy ///
    idealpoint_abs_distance post_2019

display "FINAL_DATA_VALIDATION=PASSED"
display "NO_ESTIMATION_COMMANDS_EXECUTED=1"
log close
