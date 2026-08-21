# CacheSweep 外置软件缓存规则库规格说明

本文档配套以下三个文件，说明规则库的数据格式、风险分级、路径写法与扩展方法：

| 文件 | 作用 |
| --- | --- |
| `software_cache_rules.json` | 内置规则库（随程序分发） |
| `user_rules_template.json` | 用户自定义规则模板（纯 JSON，复制改名为 `user_rules.json` 后生效） |
| `rule_loader.py` | 独立加载/扫描模块，供主程序 `import` 调用 |

---

## ① JSON 每个字段完整释义

规则文件顶层结构：

```json
{
  "schema_version": "1.0",
  "rules": [ { ...每条规则... } ]
}
```

每条规则（`rules` 数组元素）包含以下字段：

| 字段 | 类型 | 必填 | 释义 |
| --- | --- | --- | --- |
| `app_name` | string | 是 | 软件显示名，例如 `Chrome`、`微信`。扫描结果中直接展示。 |
| `app_alias` | string[] | 否 | 别名数组，用于搜索/匹配，例如 `["Google Chrome", "谷歌浏览器"]`。 |
| `category` | string | 是 | 分类标签，例如 `浏览器缓存`、`开发工具`、`即时通讯`。 |
| `glob_patterns` | string[] | 是 | 待扫描的目录路径模式，支持环境变量与 glob 通配符（见 ③）。 |
| `exclude_patterns` | string[] | 否 | 从 `glob_patterns` 匹配结果中排除的路径模式，用于屏蔽核心配置目录。 |
| `risk_level` | string | 是 | 风险等级，仅允许 `safe` / `caution` / `forbidden` 三个枚举值（见 ②）。 |
| `default_check` | boolean | 是 | UI 默认是否勾选。`safe` 建议 `true`，`caution`/`forbidden` 建议 `false`。 |
| `confidence` | string | 否 | 路径可信度：`high` / `medium` / `low`。`low` 表示待人工本机核验。 |
| `note` | string | 否 | 说明文字：删除影响、注意事项、待核验提示等，扫描结果中展示。 |

补充说明：

- `forbidden` 条目**仍然可以写进 JSON**，但它的作用只是“黑名单记录”；`rule_loader.load_rules()` 会在读取阶段就把它们**彻底过滤**，不会返回给上层，也不会参与扫描（见 ② 与 ⑥）。
- `confidence` 是本规则库新增的扩展字段，用于标注路径是否经公开资料核实、还是仅凭推测，便于人工复核。
- JSON 必须是**标准 JSON**（不含注释、不含尾逗号），因为 `rule_loader` 使用 `json.load()` 解析。需要写说明时，放到 `note` 字段或本文档。

---

## ② safe / caution / forbidden 三级风险判定标准

| 等级 | 含义 | 删除后果 | 处理方式 | default_check |
| --- | --- | --- | --- | --- |
| `safe` | 程序可自动重建的临时/缓存数据 | 不丢失账号、登录态、配置、聊天记录 | 正常参与扫描并展示 | `true` |
| `caution` | 可以清理，但会丢失本地图片、日志、本地会话缓存或恢复点 | 丢失本地接收文件 / 未保存恢复点 / 窗口布局等 | 正常展示，但默认不勾选，需用户确认 | `false` |
| `forbidden` | 账号、登录凭证、软件核心配置、聊天记录数据库 | 丢失即无法找回，甚至导致需重新登录 | **扫描阶段直接过滤，绝不展示给 UI 用户** | `false` |

判定原则：

1. 优先判断“删除后是否需要重新登录 / 是否会丢失无法再生的数据”。是 → `forbidden`。
2. 其次判断“是否只丢本地图片/日志/会话缓存，核心账号与配置无损”。是 → `caution`。
3. 仅当“程序会在下次启动自动重建、且不涉及任何账号/配置/用户数据”时，才标 `safe`。

> 同一软件可以有多条规则，例如“微信图片视频缓存 = caution”与“微信聊天记录库 = forbidden”并存，二者互不冲突。

---

## ③ glob 路径写法与 Windows 环境变量说明

### 支持的环境变量（`%VAR%` 形式，大小写不敏感）

| 变量 | 典型值 | 用途 |
| --- | --- | --- |
| `%LOCALAPPDATA%` | `C:\Users\<user>\AppData\Local` | 绝大多数软件缓存（Chrome/Edge/pip/npm/NVIDIA 等） |
| `%APPDATA%` | `C:\Users\<user>\AppData\Roaming` | 配置目录（VSCode/Cursor/WPS 等） |
| `%USERPROFILE%` | `C:\Users\<user>` | 微信/QQ 的 `Documents` 下的数据 |
| `%TEMP%` | `C:\Users\<user>\AppData\Local\Temp` | 用户临时目录 |
| `%TMP%` | 同 `%TEMP%` | 备用的临时目录变量 |
| `%ProgramData%` | `C:\ProgramData` | NVIDIA `NV_Cache` 等共享数据 |
| `%SystemDrive%` | `C:` | 盘符引用 |

> `%TEMP%` 等价于 `%LOCALAPPDATA%\Temp`，规则库只写 `%TEMP%` 一条，避免重复扫描同一目录。
> 变量若在本机不存在，`rule_loader` 会跳过该条规则而不会崩溃。

### glob 通配符

| 符号 | 含义 | 示例 |
| --- | --- | --- |
| `*` | 匹配该路径段内的任意字符（不含 `\` 分隔符），也常用于匹配动态目录名 | `User Data\*` 匹配 `Default`、`Profile 1`；`WeChat Files\*` 匹配 `wxid_xxx` |
| `?` | 匹配单个字符 | `file?.log` |
| `[abc]` | 匹配括号内任一字符 | `[Cc]ache` |

要点：

- **路径大小写不敏感**：`Chrome` 与 `chrome` 视为同一路径。`rule_loader` 使用 `fnmatch`/`glob` 的 `normcase` 机制保证这一点。
- **`*` 不会跨目录层级**：`%APPDATA%\Code\*` 只匹配 `Code` 的直接子项，不会递归到更深层；需要枚举多级时逐级写 `*`。
- **不要写 `**`**：本规则库不需要递归 glob，逐级 `*` 已够用，避免误伤与性能问题。
- **反斜杠写法**：JSON 字符串中 `\` 必须写成 `\\`，例如 `"%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Cache"`。

### `exclude_patterns` 的匹配语义

- 同样支持环境变量与 glob 通配符。
- 对 `glob_patterns` 展开后的**每一个真实路径**做**全路径** glob 匹配，命中即排除，大小写不敏感。
- 用途：当 `glob_patterns` 较宽（如某个软件的 Roaming 根目录）时，用 `exclude_patterns` 把 `settings.json`、`Login Data`、`Cookies` 等核心配置挡在扫描之外。

---

## ④ 手把手：如何新增自定义软件规则

1. **复制模板**：把 `user_rules_template.json` 复制一份，改名为 `user_rules.json`（放在项目根目录，与 `rule_loader.py` 同级）。

2. **编辑规则**：用文本编辑器（UTF-8 编码）打开 `user_rules.json`，保留顶层结构 `{ "schema_version": "1.0", "rules": [ ... ] }`，在 `rules` 数组里增删条目。

3. **填写字段**：按 ① 的字段表填写，重点：
   - `glob_patterns` 只写该软件**明确的缓存目录**，用 `%LOCALAPPDATA%` 等变量，别写盘符根目录。
   - 先判断风险等级，再决定 `default_check`。
   - 拿不准的路径把 `confidence` 填 `"low"`，在 `note` 里写“待本机核验”。

4. **核验路径**：在“文件资源管理器”地址栏粘贴展开后的真实路径（把 `%VAR%` 换成 `echo %VAR%` 的输出），确认目录存在、内容确为缓存。

5. **生效方式**：无需改代码。`rule_loader.load_rules()` 会自动读取 `user_rules.json` 并与内置规则合并；`forbidden` 条目仍会被过滤。

6. **示例**（在 `rules` 数组内新增一条）：

   ```json
   {
     "app_name": "我的软件",
     "app_alias": ["MyApp"],
     "category": "自定义",
     "glob_patterns": ["%LOCALAPPDATA%\\MyApp\\cache"],
     "exclude_patterns": ["%LOCALAPPDATA%\\MyApp\\config"],
     "risk_level": "safe",
     "default_check": true,
     "confidence": "low",
     "note": "待本机核验。"
   }
   ```

> 注意：JSON 不允许写 `//` 注释，也不允许数组最后一个元素后有多余逗号，否则 `load_rules()` 会跳过整个文件。

---

## ⑤ 黑名单清单：永远禁止加入规则库的目录

以下系统/配置目录**绝对不能**出现在任何 `glob_patterns` 中（即便标 `forbidden` 也应避免，防止误删导致系统或账号不可用）：

- 系统核心目录：`C:\Windows`、`C:\Windows\System32`、`C:\Windows\SysWOW64`、`C:\Windows\WinSxS`、`C:\Windows\Temp`
- 程序安装目录：`C:\Program Files`、`C:\Program Files (x86)`、`C:\ProgramData`（整体，仅允许指向其中明确的缓存子目录如 NVIDIA `NV_Cache`）
- 用户凭据与账号：`%APPDATA%\Microsoft\Credentials`、`%APPDATA%\Microsoft\Protect`、`%USERPROFILE%\.ssh`、`%USERPROFILE%\.gnupg`
- 用户配置根：`%USERPROFILE%\NTUSER.DAT*`、`%USERPROFILE%\AppData\Roaming`（整体）、`%USERPROFILE%\AppData\Local`（整体）
- 浏览器登录/历史/收藏：Chrome/Edge 的 `Login Data`、`Cookies`、`History`、`Bookmarks`、`Web Data`
- 聊天记录与账号库：微信 `FileStorage\Msg`、`MsgAttach`，QQ 的 `Msg*`、`nt_qq`、`%APPDATA%\Tencent\QQ`
- 软件核心配置：VSCode/Cursor 的 `User\settings.json`、`keybindings.json`、`snippets`、`globalStorage`
- 盘符根目录：`C:\`、`D:\` 等任何盘符根，以及 `%SystemDrive%\`（`rule_loader` 会主动拦截这类前缀）

原则：**只允许指向“可再生的缓存子目录”，任何“整体配置/账号/系统目录”一律禁止。**

---

## ⑥ rule_loader.py 对外 API

```python
from rule_loader import load_rules, scan_by_rules

rules = load_rules()      # -> List[dict]
results = scan_by_rules(rules)  # 缺省内部也会调用 load_rules()
```

### `load_rules() -> list[dict]`

- 读取 `software_cache_rules.json` + `user_rules.json`（后者不存在则忽略）。
- 返回字段：`app_name / app_alias / category / glob_patterns / exclude_patterns / risk_level / default_check / confidence / note`。
- **已彻底过滤 `forbidden` 条目与非法条目**，上层永远看不到它们。

### `scan_by_rules(rules=None) -> list[dict]`

- 对每条规则展开环境变量 → glob 匹配 → 应用 `exclude_patterns` → 统计目录。
- 返回每项字段：`app_name / category / real_path / file_count / size_bytes / risk_level / note / default_check`。
- 同一真实路径跨规则**去重**，只保留首次命中。
- 异常策略：环境变量缺失、路径访问拒绝、单文件被占用、JSON 损坏等均**只跳过对应项，绝不抛出异常**。

### 性能与安全提示

- `scan_by_rules()` 只遍历规则给出的目录前缀，**绝不递归盘符根目录**，且对盘符根/系统目录做了主动拦截。
- `os.scandir` 默认 `follow_symlinks=False`，不会陷入目录联接（junction）循环。
- pip/npm/NVIDIA/Temp 目录可能很大，建议主程序在**工作线程**中调用 `scan_by_rules()`（现有 `cache_manager.py` 已用 `threading.Thread` 跑扫描，可复用该模式）。

---

## 附：路径来源与参考

规则库中的路径依据以下公开资料整理，`confidence` 已按资料可信度标注；`low` 项请在本机核验后再实际清理：

- Chrome 缓存：<https://www.vicarius.io/vsociety/posts/clear-google-chrome-browser-cache-browser-management>；<https://www.cnblogs.com/yangykaifa/p/19279049>
- Edge 缓存：<https://github.com/duplicati/duplicati/issues/4160>；<http://ftp.wisecleaner.com/how-to/379-how-to-clear-web-browser-cache-in-windows-11.html>
- VSCode 缓存：<https://www.php.cn/faq/2603234.html>；<https://github.com/microsoft/vscode/issues/183344>
- Cursor 缓存：<https://forum.cursor.com/t/can-the-default-cache-location-be-changed/16204>；<https://github.com/d-padmanabhan/agent-engineering-handbook/blob/main/scripts/cursor-maintenance.sh>
- pip 缓存：<https://pip.pypa.io/en/stable/topics/caching/>
- npm 缓存：<https://docs.npmjs.com/cli/v10/commands/npm-cache>；<https://github.com/npm/cli/commit/997bcdf8d4fd3e5ecdd224060fb166b43c3ffb19>
- WPS 缓存：<https://bbs.wps.cn/topic/90864>；<https://blog.csdn.net/weixin_34101229/article/details/94203959>
- NVIDIA 着色器缓存：<https://nvidia.custhelp.com/app/answers/detail/a_id/5735>
- 用户 Temp 目录：<https://learn.microsoft.com/en-us/answers/questions/3806416/can-i-delete-contents-of-temp-folder-in-appdata-fo>；<https://arstechnica.com/civis/threads/user-appdata-local-temp-safe-to-delete.1511447/>
- 微信存储位置：<https://www.pconline.com.cn/ask/22055.html>；<https://cloud.tencent.com.cn/developer/article/2682373>
- QQ 存储位置：<https://www.sohu.com/a/980055252_122542616>；<https://www.cnblogs.com/pcdoctor/p/20121920>
