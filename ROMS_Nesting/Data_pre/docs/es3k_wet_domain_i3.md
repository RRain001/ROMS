# ES3K 湿海域、海峡与开放边界审计（I3）

## 科学边界

ES3K 的经纬度最大包络不是必须计算的经纬度矩形。保留已确定的四角与旋转保角候选不变；本工具只读取候选 NetCDF，不修改四角、正交性、水深或陆海掩膜。

朝鲜半岛西侧的真实海水若落在网格内部，**不得直接将其标记为陆地**。这会引入未经验证的人工固壁。应先检查 ES3K 曲线外边界形状及其和开放边界的对应，再决定是否要提出新的几何候选；如现有四角无法同时满足缩减目标，明确报告这一冲突。

## 真实数据执行方法（现在支持公开在线获取，不需要本地全球数据）

先执行在线数据子集提取：

    python ROMS_Nesting/Data_pre/scripts/nesting/fetch_es3k_online_data.py --output-dir /tmp/ES3K_ONLINE --resolution-arcsec 30 --coast-resolution h

再使用嵌套版独立生成器：

    python ROMS_Nesting/Data_pre/scripts/nesting/create_bathymetry_grid.py \
      --geometry-json ROMS_Nesting/configs/es3k_conformal_candidate.json \
      --bathymetry /tmp/ES3K_ONLINE/GEBCO_2026_ES3K_30sec.nc \
      --gshhg-base /tmp/ES3K_ONLINE/GSHHS_shp \
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

GitHub Ubuntu 工作流现在同时执行合成单测与真实公开 GEBCO2026/GSHHG237 在线子集和候选网格审计，数据源、文件及 SHA 在 manifest 中保存。真实数据成功不代表地形平滑、海峡/开放边界或 ROMS 物理验收成功。

后续 I3 必须继续：全尺寸真实 GEBCO/GSHHG 格点审计、人工海岸线与地形坡度 rx0/rx1 核验、父子湿边界验证、ROMS 1h/6h/24h/长期动力验收。完成前状态为 I3_NOT_ACCEPTED。

## 2026-10-14 全尺寸几何统计（非湿格验收）

GitHub 托管 Ubuntu [Actions #38572109520](https://github.com/RRain001/ROMS/actions/runs/38572109520) 使用既有四角保角候选的全部 732×464 RHO 点得到：

- 全网格 339,648 个 RHO；最大正交误差 0.002764823°。
- 朝鲜半岛西侧粗略观察窗（123.5–126.5°E，34–39°N）落入网格的 RHO 点：**12,097 个，占全网格约 3.56%**。
- 仅为 **geometric occupancy**（几何落点数）；缺少 GEBCO/GSHHG 海陆分类，因此不能把 12,097 称为湿格或真实计算负担。整个黄海及其他无关海域也不能据此给出总成本。
- 合成 NetCDF 的 7/7 个单元测试 PASS，真实 I3、海峡水动力、最优边界选择均 NOT RUN。

因此不应仅凭 3.56% 判定改动边界一定有收益；需要先获得真实湿格、海盆及海峡边界图和网格面积预算。


## 2026-10-14 首次真实 GEBCO 2026 + GSHHG 2.3.7 审计

[Actions #38574047637](https://github.com/RRain001/ROMS/actions/runs/38574047637) 全部通过；GEBCO 原始 15″ COG 按 30″ 平均下采样至本地网格驱动区，海岸线来自 GMT 官方 GSHHG 2.3.7 h/L1。该次数据为真实来源，但仍属于预验收。

- ES3K 732×464 RHO，总格点 339,648；湿格 213,634；湿区 metric 近似面积 1,548,004.46 km²。
- 朝鲜半岛以西仅供筛查的 123.5–126.5°E、34–39°N 窗口：几何点 12,097，实际湿点 9,564；湿区面积 79,308.58 km²。整个黄海及其他无关海区尚未完整估算，不能把此值视作全部冗余成本。
- 对马、津轻、宗谷、鞑靼四个近似海峡窗口与主海盆在 4 邻接湿格分量中均为连通；尚未检查真实海峡通道宽度、边界输运与动力过程。
- wet connected components 共 111 个，需检查小岛周边的离散水体或地形与岸线分辨率伪影。
- 未平滑湿格相邻水深坡度最大 rx0=0.930418875981242；正式计算前必须进行 bathymetry smoothing 和 rx0/rx1 检验，而不能把此网格直接视作 I3 PASS。
- 西/东/南/北四条逻辑网格边缘分别 91/462/405/350 湿点，共 1/3/14/5 个湿段；尤其南侧需要审查支离的开放边界位置。
- Actions artifact 提供实际 ES3K 候选 NetCDF、manifest、湿格和开边界 JSON。文件哈希可以从日志及 manifest 追溯；不提交大文件至 Git。
- 已另行新增原始 15″ GEBCO 2026 的全尺寸复核 CI，用于对比 30″ 下采样对海岸线和湿格的影响。直到真实分辨率复核、地形平滑和 ROMS 1h/6h/24h/长期水动力试算完成，都应维持 I3_NOT_ACCEPTED。
