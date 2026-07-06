Retail Intelligence Platform 使用说明

本项目面向服装品牌的零售分析场景，用于把 RPA 导出的业务数据沉淀为可查询、可扩展的零售数据平台。

架构：
RPA export → importer → SQLite data warehouse → query/filter layer → dashboard / future API / AI

主要数据流：
- import_master_data.py：导入商品、商店、渠道、日期维表。
- import_sales.py：导入历史/每日零售销售，写入 fact_retail_sales。

数据模型说明：
- 商品代码只作为记录标识，不作为当前业务筛选逻辑。
- 年份、季度、波段、品类、设计师等业务维度来自 dim_product。
- 查询层统一通过可复用的 filter engine 组装 SQLite 条件，再提供给仪表板、后续 API 和 AI 模块复用。

使用方式：
1. 先确认 RPA 已完成当天导出，再把相关文件放入 exports 文件夹。
2. 运行导入流程，更新 SQLite 数据仓库。
3. 通过 Dashboard 查看结果，或后续接入 API / AI 分析功能。

部署与访问：
- 本机通过 Flask / Waitress 运行。
- 对外访问通过 Cloudflare Tunnel：
  https://retail.li-disha.com

补充：
- 商品图片保存在 R:\商品部 下的多级子目录中，系统会递归查找。
- 文件名通常为 商品代码_颜色代码.jpg / .png / .jpeg / .webp / .bmp。
- 这个说明文档面向内部使用，重点是数据导入、查询和访问路径，不再描述旧的单页商品分析逻辑。
