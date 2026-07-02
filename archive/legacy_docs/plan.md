`MULTIFILE_INFO_S2D` 属于 ROMS/COAWST 的 `check_multifile.F` 检查逻辑，主要处理二维 surface forcing 多文件信息；源码检索结果也显示它会搜索 time variable，并在处理文件失败时报 `MULTIFILE_INFO_S2D - Error while processing ...`。这和 `roms_bdy_202401.nc`、HYCOM thin-band boundary 的关系不大。ROMS 输入文件里的 `NFFILES` 是 forcing 文件数量，`FRCNAME` 是 forcing 文件列表；ROMS 本身也支持多个 surface forcing 文件。

你现在最应该做的是先复跑一次，不要再改 HYCOM：

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m/run
./run_pilot_1day.sh

tail -160 /home/lhy/ROMS/projects/fukushima_202401_50m/output/pilot_1day_run.log
```

如果已经过了，说明补 `time` 属性有效，下一步就可以看是否积分到 `ROMS: DONE`。如果仍然停在 `MULTIFILE_INFO_S2D`，按下面顺序查。

第一，确认 external `.in` 里的 forcing 文件数量和文件列表严格一致：

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m/run

grep -nE 'NFFILES|FRCNAME|NCLMFILES|CLMNAME|NBCFILES|BRYNAME|ININAME|GRDNAME|TIME_REF|DSTART' \
  ocean_fukushima_202401_pilot_1day.in
```

重点看：

```text
NFFILES == 2
FRCNAME == .../roms_atm_202401.nc \
           .../roms_rad_202401.nc
```

如果 `NFFILES=2`，但 `FRCNAME` 由于换行、反斜杠、空格、引号问题只被 ROMS 读到 1 个文件，或者读到了错误路径，就会进入 `check_multifile` 报错。最稳妥的写法通常是让 `FRCNAME` 两个文件分两行，且第一行末尾带 `\`，不要有中文注释或多余字符。

第二，直接检查两个 forcing 文件的变量、维度、`time` 属性：

```bash
cd /home/lhy/ROMS/projects/fukushima_202401_50m

ncdump -h input/roms_atm_202401.nc | sed -n '1,220p'
ncdump -h input/roms_rad_202401.nc | sed -n '1,220p'
```

ROMS surface forcing 变量通常需要满足这种结构：

```text
dimensions:
  sms_time = UNLIMITED or fixed ;
  eta_rho = ... ;
  xi_rho = ... ;

variables:
  double sms_time(sms_time) ;
    sms_time:long_name = "surface momentum stress time" ;
    sms_time:units = "days since 1858-11-17 00:00:00" ;
    sms_time:calendar = "gregorian" ;

  float sustr(sms_time, eta_u, xi_u) ;
    sustr:time = "sms_time" ;
```

或者所有 forcing 统一用一个 `time(time)` 也可以，但要保证每个二维 forcing 变量的 `:time` 属性指向真实存在的一维时间变量。例如：

```text
float Pair(time, eta_rho, xi_rho) ;
  Pair:time = "time" ;
```

第三，确认所有 forcing 变量的 `time` 属性真的存在，而且指向存在的一维变量：

```bash
python3 - <<'PY'
from netCDF4 import Dataset
from pathlib import Path

for p in [
    Path("/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_atm_202401.nc"),
    Path("/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_rad_202401.nc"),
]:
    print("\n==", p.name, "==")
    ds = Dataset(p)
    one_d = {name for name, v in ds.variables.items() if len(v.dimensions) == 1}
    print("1D vars:", sorted(one_d))
    for name, v in ds.variables.items():
        if len(v.dimensions) >= 3:
            tattr = getattr(v, "time", None)
            print(name, "dims=", v.dimensions, "time_attr=", tattr)
            if not tattr:
                print("  ERROR: missing :time attribute")
            elif tattr not in ds.variables:
                print("  ERROR: time attr points to missing variable")
            elif len(ds.variables[tattr].dimensions) != 1:
                print("  ERROR: time variable is not 1D")
    ds.close()
PY
```

第四，确认 forcing 时间覆盖 `DSTART=0.5d0`。你的 ocean 窗口是 `2024-01-01T12:00:00` 起，`pilot_1day` 如果从这个时间起跑，forcing 必须覆盖这一天。建议直接打印时间值：

```bash
python3 - <<'PY'
from netCDF4 import Dataset, num2date
from pathlib import Path

for p in [
    Path("/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_atm_202401.nc"),
    Path("/home/lhy/ROMS/projects/fukushima_202401_50m/input/roms_rad_202401.nc"),
]:
    print("\n==", p.name, "==")
    ds = Dataset(p)
    for name, v in ds.variables.items():
        if len(v.dimensions) == 1 and ("time" in name.lower() or name.endswith("_time")):
            units = getattr(v, "units", None)
            cal = getattr(v, "calendar", "standard")
            vals = v[:]
            print(name, "len=", len(vals), "first=", vals[0], "last=", vals[-1], "units=", units)
            if units:
                print("  dates:", num2date([vals[0], vals[-1]], units, calendar=cal))
    ds.close()
PY
```

第五，如果仍报错，把日志中 `MULTIFILE_INFO_S2D` 前后 80 行截出来：

```bash
grep -n -B80 -A80 'MULTIFILE_INFO_S2D' \
  /home/lhy/ROMS/projects/fukushima_202401_50m/output/pilot_1day_run.log
```

我的优先判断是：**还有某个 forcing 变量没有正确的 `:time` 属性，或者 `FRCNAME/NFFILES` 的多文件写法没有被 ROMS 正确解析**。先不要回退 HYCOM boundary，不要重新生成 `roms_bdy_202401.nc`；现在应集中查 `roms_atm_202401.nc`、`roms_rad_202401.nc` 和 external `.in` 的 forcing 段。
