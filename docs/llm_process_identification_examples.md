# LLM 过程识别示例：Stage 1A、Stage 1B 与 Stage 2

附表 1 至附表 10 采用与示例文献相同的呈现逻辑：左侧列示条款信息，右侧列示模型推理过程，底部给出分类结果与判断理由。该形式用于直观展示 LLM 识别框架并非简单依赖关键词或章节名称，而是逐层判断条款文本是否包含制度内容、制度内容属于何种机制，以及该机制是否直接作用于贸易或投资渠道。

## 附表 1 被正确识别为【非制度型开放】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Export Quotas &amp; Quantitative Restrictions</td><td rowspan="3">LLM 推理<br>过程简述</td><td rowspan="3">模型面对含有 export quotas 和 quantitative restrictions 的文本时，并未仅凭关键词作出肯定判断，而是先识别其文本形态：该条只是章节或条款标题，没有给出禁止、允许、例外、程序、机构、义务或适用条件。因此，模型认为其不能独立构成可执行的制度安排。</td></tr>
<tr><td>政策领域</td><td>Export Restrictions</td></tr>
<tr><td>原始编码</td><td>Export Restrictions - prov_01</td></tr>
<tr><td>分类结果</td><td colspan="3">0（非制度型开放）</td></tr>
<tr><td>判断理由</td><td colspan="3">该条款只提供主题标签，不包含实体义务、行政程序、监管条件或技术标准。若采用关键词法，容易因为出现“出口配额/数量限制”而误判为制度型开放；LLM 则能识别其标题性质。</td></tr>
</table>

## 附表 2 被正确识别为【制度型开放】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Prohibits all export quotas / QRs between the Parties, without reference to exceptions within the provision</td><td rowspan="3">LLM 推理<br>过程简述</td><td rowspan="3">模型首先识别出该条同样涉及出口配额和数量限制，但进一步捕捉到 Prohibits 这一禁止性谓词。该文本明确规定缔约方之间不得实施出口配额或数量限制，直接设定实体性贸易自由化义务，不同于单纯标题或目录项。</td></tr>
<tr><td>政策领域</td><td>Export Restrictions</td></tr>
<tr><td>原始编码</td><td>Export Restrictions - prov_03</td></tr>
<tr><td>分类结果</td><td colspan="3">1（制度型开放）</td></tr>
<tr><td>判断理由</td><td colspan="3">该条款直接回答“什么被禁止”，并对缔约方行为形成可执行约束，构成明确的制度安排。它与附表 1 形成同关键词、不同文本功能的对照。</td></tr>
</table>

## 附表 3 被正确识别为【实体规则（rules）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Prohibits all export quotas / QRs between the Parties, without reference to exceptions within the provision</td><td rowspan="3">LLM 推理<br>过程简述</td><td rowspan="3">模型将核心语义定位为禁止缔约方实施出口配额或数量限制。该条款直接回答“什么被禁止”以及缔约方承担何种法律义务，不涉及行政办理流程、机构设置、监管条件或技术尺度。</td></tr>
<tr><td>政策领域</td><td>Export Restrictions</td></tr>
<tr><td>原始编码</td><td>Export Restrictions - prov_03</td></tr>
<tr><td>分类结果</td><td colspan="3">rules（实体规则）</td></tr>
<tr><td>判断理由</td><td colspan="3">条款的制度功能是确立实体性禁止义务，因此归入 rules。这说明模型不仅识别贸易限制主题，还能进一步区分其制度作用机制。</td></tr>
</table>

## 附表 4 被正确识别为【行政管理（management）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Release good within prescribed time limits</td><td rowspan="3">LLM 推理<br>过程简述</td><td rowspan="3">模型把识别重点放在 prescribed time limits 上，认为该条款规范的是海关放行货物的办理流程和完成时限。其核心问题是政府如何组织和实施通关事务，而不是规定产品技术条件或市场准入实体资格。</td></tr>
<tr><td>政策领域</td><td>Trade Facilitation and Customs</td></tr>
<tr><td>原始编码</td><td>Trade Facilitation and Customs - prov_31</td></tr>
<tr><td>分类结果</td><td colspan="3">management（行政管理）</td></tr>
<tr><td>判断理由</td><td colspan="3">该条款属于海关行政程序和办事效率安排，直接对应“由谁、按什么流程、在何时实施”的管理维度。</td></tr>
</table>

## 附表 5 被正确识别为【监管规制（regulation）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Does the agreement regulates state aid?</td><td rowspan="3">LLM 推理<br>过程简述</td><td rowspan="3">模型识别出 state aid 指向政府对国家援助、补贴或类似市场行为的监管约束。该条款的制度功能是限制或监督特定经济活动，而不是单纯规定实体待遇、行政办理流程或技术标准。</td></tr>
<tr><td>政策领域</td><td>Competition Policy</td></tr>
<tr><td>原始编码</td><td>Competition Policy - prov_20</td></tr>
<tr><td>分类结果</td><td colspan="3">regulation（监管规制）</td></tr>
<tr><td>判断理由</td><td colspan="3">国家援助规制属于竞争政策中对政府援助行为和市场竞争条件的监管约束，因此归入 regulation。</td></tr>
</table>

## 附表 6 被正确识别为【技术标准（standards）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Do parties reference international standards?</td><td rowspan="3">LLM 推理<br>过程简述</td><td rowspan="3">模型识别出该条款的核心不是一般 SPS 监管，而是是否引用 international standards。引用国际标准的制度功能在于确定卫生与植物卫生措施的技术依据和合规基准。</td></tr>
<tr><td>政策领域</td><td>Sanitary and Phytosanitary Measures (SPS)</td></tr>
<tr><td>原始编码</td><td>Sanitary and Phytosanitary Measures (SPS) - prov_11</td></tr>
<tr><td>分类结果</td><td colspan="3">standards（技术标准）</td></tr>
<tr><td>判断理由</td><td colspan="3">该条款以国际标准作为技术尺度或符合性依据，属于 standards。这避免了把 SPS 章节中的所有条款一概归为监管规制。</td></tr>
</table>

## 附表 7 被正确识别为【贸易渠道（mp）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Freedom of transit for goods</td><td rowspan="4">LLM 推理<br>过程简述</td><td rowspan="4">模型将制度对象识别为跨境货物。Freedom of transit for goods 直接规范货物运输、通关和跨境流动条件，不涉及外国投资者、商业存在、资本转移或投资待遇。</td></tr>
<tr><td>政策领域</td><td>Trade Facilitation and Customs</td></tr>
<tr><td>原始编码</td><td>Trade Facilitation and Customs - prov_25</td></tr>
<tr><td>Stage 1B 维度</td><td>rules</td></tr>
<tr><td>分类结果</td><td colspan="3">mp（贸易渠道）；贸易权重 1.0，投资权重 0.0</td></tr>
<tr><td>判断理由</td><td colspan="3">货物过境自由直接作用于货物贸易流动，属于贸易渠道；同时缺乏投资者或商业存在对象，因此不计入投资渠道。</td></tr>
</table>

## 附表 8 被正确识别为【投资渠道（tr）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Does the agreement include a definition of &quot;investor&quot;?</td><td rowspan="4">LLM 推理<br>过程简述</td><td rowspan="4">模型识别出 investor definition 是投资章节的核心适用对象边界，决定哪些主体享有投资协定保护或承担相应义务。文本没有指向货物、跨境服务交易或贸易支付。</td></tr>
<tr><td>政策领域</td><td>Investment</td></tr>
<tr><td>原始编码</td><td>Investment - prov_07</td></tr>
<tr><td>Stage 1B 维度</td><td>rules</td></tr>
<tr><td>分类结果</td><td colspan="3">tr（投资渠道）；贸易权重 0.0，投资权重 1.0</td></tr>
<tr><td>判断理由</td><td colspan="3">该条款直接界定外国投资者这一投资制度对象，属于投资渠道。它展示了 LLM 不只是按 Investment 章节归类，还能说明具体的作用机制。</td></tr>
</table>

## 附表 9 被正确识别为【贸易与投资兼具（both）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Please indicate which one of the following dispute settlement provision apply to the  services agreement? <br>A.  State-state dispute settlement; <br>B.  Investors-state dispute setllement; <br>C.  Both</td><td rowspan="4">LLM 推理<br>过程简述</td><td rowspan="4">模型识别出服务协定争端解决机制同时列明国家间争端解决和投资者-国家争端解决。前者通常对应跨境服务贸易争端，后者明确对应外国投资者或商业存在，故该条款同时覆盖服务贸易和投资救济。</td></tr>
<tr><td>政策领域</td><td>Services</td></tr>
<tr><td>原始编码</td><td>Services - dispute</td></tr>
<tr><td>Stage 1B 维度</td><td>rules</td></tr>
<tr><td>分类结果</td><td colspan="3">both（贸易与投资兼具）；贸易权重 0.5，投资权重 0.5</td></tr>
<tr><td>判断理由</td><td colspan="3">该条款虽位于 Services 章节，但其选项中明确出现 investor-state dispute settlement，直接指向服务业商业存在和投资者保护，因此不能只判为贸易渠道。</td></tr>
</table>

## 附表 10 被正确识别为【非贸易/非投资渠道（none）】的 DTA 条款

<table>
<tr><th colspan="2">条款信息</th><th colspan="2">模型推理</th></tr>
<tr><td>条款文本</td><td>Does the agreement require states to facilitate civil society involvement and/or establish a forum on trade and environment?</td><td rowspan="4">LLM 推理<br>过程简述</td><td rowspan="4">模型注意到条款中出现 trade and environment，但进一步判断其制度内容只是促进公民社会参与或建立论坛。该机制属于一般环境治理、对话和参与安排，未直接规范货物、服务、外国供应商、投资者、商业存在或资本流动。</td></tr>
<tr><td>政策领域</td><td>Environmental Laws</td></tr>
<tr><td>原始编码</td><td>Environmental Laws - prov_53</td></tr>
<tr><td>Stage 1B 维度</td><td>management</td></tr>
<tr><td>分类结果</td><td colspan="3">none（非贸易/非投资渠道）；贸易权重 0.0，投资权重 0.0</td></tr>
<tr><td>判断理由</td><td colspan="3">该条款具有制度性管理安排，但无法识别直接贸易对象或直接投资对象。关键词法可能因出现 trade 而误判为贸易渠道，LLM 则能识别其真实功能是环境治理协商机制。</td></tr>
</table>

## 可写入论文的方法说明

上述过程识别示例表明，LLM 编码框架并非简单依据关键词或章节名称分类。Stage 1A 先判断文本是否真正包含可执行的制度内容，避免把标题、目录项或一般宣示误判为制度型开放；Stage 1B 再判断制度内容的作用机制，区分实体规则、行政实施、监管约束和技术标准；Stage 2 最后判断制度安排的直接作用对象，区分货物/服务贸易、投资者/商业存在、二者兼具，以及一般治理机制。

因此，该方法相较传统关键词法或单纯章节归类具有两点优势：第一，它能处理“同词不同义”的情形，例如同样出现 export quotas 时区分标题与禁止性义务；第二，它能处理“同章不同渠道”的情形，例如服务章节中同时识别跨境服务贸易与商业存在，或在环境章节中识别不直接作用于贸易/投资的治理机制。
