# ES3K 湿海域、海峡与开放边界审计（I3）

## 科学边界

ES3K 的经纬度最大包络不是必须计算的经纬度矩形。保留已确定的四角与旋转保角候选不变；本工具只读取候选 NetCDF，不修改四角、正交性、水深或陆海掩膜。

朝鲜半岛西侧的真实海水若落在网格内部，**不得直接将其标记为陆地**。这会引入未经验证的人工固壁。应先检查 ES3K 曲线外边界形状及其和开放边界的对应，再决定是否要提出新的几何候选；如现有四角无法同时满足缩减目标，明确报告这一冲突。

## 真实数据执行方法（需要主机已有 GEBCO/GSHHG）

先使用嵌套版独立生成器：

    python ROMS_Nesting/Data_pre/scripts/nesting/create_bathymetry_grid.py \
      --geometry-json ROMS_Nesting/configs/es3k_conformal_candidate.json \
      --bathymetry /workspace/GEBCO/GEBCO_2026.nc \
      --gshhg-base /workspace/GSHHG/gshhg-shp-2/GSHHS_shp \
      --gshhg-resolution h \
      --output /tmp/ES3K_real_candidate.nc

再运行只读诊断：

    python ROMS_Nesting/Data_pre/scripts/nesting/audit_es3k_wet_domain.py \
      --grid /tmp/ES3K_real_candidate.nc \
      --report-json /tmp/ES3K_wet_domain_audit.json

可选参数 --strict-no-yellow-sea-wet 在西侧近似观察窗有湿格时返回退出码 2，绝不修改源文件。不要使用 --allow-gebco-only-mask 冒充真实 GSHHG 验收。

## 指标

1. 总湿格数量与面积按 ROMS pm/pn 计算。陆地格虽被掩膜，仍属于模型数组，湿格数不能等同全部计算开销。
2. 朝鲜半岛以西 123.5–126.5°E、34–39°N **矩形窗口**仅供侦测明显的黄海冗余；它不是黄海科学边界，不能被直接用于掩膜或区域积分。零湿格也不能证明黄海已全部排除。
3. 日本海主海盆与对马、津轻、宗谷和鞑靼海峡使用粗略地理窗口及 4 邻接湿格分量做连通检查。窗口有湿格不等于海峡水路真实通畅或交换正确；断连应重点排查。海峡检查还需要真实 GIS 海岸线、通道宽度和海流验证。
4. 四条逻辑边界记录连续湿点段和对应格点下标，后续须审查开放边界的真实海域位置及水动力边界条件。
5. 验证 mask_u/mask_v/mask_psi 与 mask_rho 一致，不直接修改任何掩膜。
6. 出现多湿分量、断连海峡或朝鲜半岛西侧湿格时报告 REVIEW_REQUIRED；未触发时只报告 NO_FLAGS_DIAGNOSTIC_ONLY，**都不是 I3 科学验收通过**。

## 结果限制

GitHub Ubuntu 工作流仅对合成 NetCDF 进行代码级测试，没有 GEBCO 2026/GSHHG 实际文件。代码不根据文件名自称真实数据已验收，数据来源和 SHA 仍需单独验证。

后续 I3 必须继续：全尺寸真实 GEBCO/GSHHG 格点审计、人工海岸线与地形坡度 rx0/rx1 核验、父子湿边界验证、ROMS 1h/6h/24h/长期动力验收。完成前状态为 I3_NOT_ACCEPTED。

## 2026-10-14 全尺寸几何统计（非湿格验收）

GitHub 托管 Ubuntu [Actions #38572109520](https://github.com/RRain001/ROMS/actions/runs/38572109520) 使用既有四角保角候选的全部 732×464 RHO 点得到：

- 全网格 339,648 个 RHO；最大正交误差 0.002764823°。
- 朝鲜半岛西侧粗略观察窗（123.5–126.5°E，34–39°N）落入网格的 RHO 点：**12,097 个，占全网格约 3.56%**。
- 仅为 **geometric occupancy**（几何落点数）；缺少 GEBCO/GSHHG 海陆分类，因此不能把 12,097 称为湿格或真实计算负担。整个黄海及其他无关海域也不能据此给出总成本。
- 合成 NetCDF 的 7/7 个单元测试 PASS，真实 I3、海峡水动力、最优边界选择均 NOT RUN。

因此不应仅凭 3.56% 判定改动边界一定有收益；需要先获得真实湿格、海盆及海峡边界图和网格面积预算。
