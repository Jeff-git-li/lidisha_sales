Retail Intelligence Platform 使用说明

Retail Intelligence Platform is a data platform designed for fashion retail brands.

It automatically imports ERP exports, builds a normalized data warehouse, provides reusable semantic queries, and powers dashboards, AI analytics, and future APIs.
1. 安装 Python 3.12 或以上。
2. 启动前先确认 RPA 已完成当天数据导出。
3. 将 RPA 导出的销售文件、主数据文件放入 exports 文件夹，然后运行导入流程。

当前架构：
RPA 导出 → 导入器 → SQLite warehouse → 查询层 → Dashboard / Future AI / API

数据流说明：
- 销售导入：把每日销售明细写入事实表 fact_retail_sales。
- 主数据导入：同步商品、颜色、门店、区域等基础信息。
- 归一化维表：业务属性统一落到 normalized dimensions，供查询层直接使用。
- 查询层：通过可复用的 query/filter engine 组装 SQLite 查询，避免在业务逻辑里直接处理原始表结构。

部署方式：
- 本机通过 Flask / Waitress 运行。
- Cloudflare Tunnel 对外暴露访问地址。
- 内网或外网访问时，都以隧道地址为准。

常见文件与路径：
- 销售文件：exports 下的日常销售导出文件。
- 主数据文件：exports 下的商品、门店、区域等基础数据文件。
- 图片目录：R:\商品部 下的多级子目录，系统会递归查找商品图片。
- 图片命名：商品代码_颜色代码.jpg / .png / .jpeg / .webp / .bmp，例如 KU21T1013_722.jpg。

运行与访问：
- 双击 run_dashboard.bat 启动。
- 本机访问：http://127.0.0.1:5000
- 外网访问：通过 Cloudflare Tunnel 提供的域名访问。

说明：
- 这个版本不再依赖“只保留 K 开头商品”之类的旧规则。
- 也不再使用基于商品代码前缀的业务逻辑来驱动查询。
- Top20、区域、品类、商品分析等页面都应通过 SQLite 查询层获取数据。
- 后续会继续扩展 API 和 AI 分析模块，但底层仍然复用同一套导入与查询体系。
