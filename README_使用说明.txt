零售销售Top20 Flask Dashboard 使用说明

1. 安装Python 3.10或以上。
2. 把RPA每天导出的“零售销售分析*.xlsx”放到本文件夹下的 exports 文件夹。
   系统会自动读取 exports 中最新的 xlsx 文件。
3. 商品图片放在 R:\商品部 下面任意多级文件夹都可以。
   文件名规则：商品代码_颜色代码.jpg / .png / .jpeg / .webp / .bmp
   例如：KU21T1013_722.jpg
4. 双击 run_dashboard.bat。
5. 本机打开：http://127.0.0.1:5000
6. 局域网其他人访问：http://你的电脑IP:5000
   如果打不开，需要在Windows防火墙允许 Python 或开放 5000 端口。

常见修改：
- 图片目录不是 R:\商品部：编辑 run_dashboard.bat，把 --image-root 后面的路径改掉。
- 端口被占用：编辑 run_dashboard.bat，把 --port 5000 改成 5050 等。
- 每天定时刷新：让RPA导出文件覆盖/新增到 exports 文件夹，然后网页点“刷新数据”。

当前支持：
- 全国Top款号
- 款色Top
- 北区/中区/南区/全国Top20
- 品类Top20
- 区域贡献
- 品类贡献
- 爆款矩阵
