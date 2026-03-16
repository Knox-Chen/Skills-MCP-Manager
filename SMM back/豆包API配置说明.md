# 豆包 API 配置说明（所有 LLM 均使用豆包）

本项目的 **HyDE 生成** 和 **智能重排** 都通过豆包（火山方舟）完成，需要在本地填写两个配置。

---

## 在哪里填写 API

在项目根目录的 **`.env`** 文件中填写（没有则复制 `.env.template` 为 `.env` 再改）：

```env
# ① 豆包 API Key
DOUBAO_API_KEY=你的API_Key

# ② 豆包推理接入点 ID（ep- 开头）
DOUBAO_ENDPOINT_ID=ep-xxxxxxxx
```

**不要**把 `.env` 提交到 git，避免泄露密钥。

---

## 如何获取这两个值

### 1. DOUBAO_API_KEY（API Key）

1. 打开 [火山方舟](https://console.volcengine.com/ark) 并登录
2. 进入 **API Key 管理**（或 访问控制 → API Key）
3. 点击 **创建 API Key**，复制生成的 Key
4. 粘贴到 `.env` 的 `DOUBAO_API_KEY=` 后面

### 2. DOUBAO_ENDPOINT_ID（推理接入点 ID）

1. 在火山方舟控制台进入 **模型推理** → **在线推理**
2. 点击 **创建推理接入点**
3. 选择豆包模型（如 **Doubao-pro-32k** 或 **Doubao-lite-32k**）并创建
4. 创建完成后在列表中找到 **接入点 ID**（形如 `ep-20241118123456-xxxxx`）
5. 复制到 `.env` 的 `DOUBAO_ENDPOINT_ID=` 后面

---

## 可选：使用旧变量名

若你已在用火山相关变量，可继续使用（与上面二选一即可）：

- `VOLC_API_KEY` 等价于 `DOUBAO_API_KEY`
- `VOLC_ENDPOINT_ID` 等价于 `DOUBAO_ENDPOINT_ID`
- `VOLC_BASE_URL` 可选，默认 `https://ark.cn-beijing.volces.com/api/v3`

---

## 填写完成后

在项目目录执行：

```powershell
.\.venv\Scripts\Activate.ps1
python recommend.py
```

若报错「未配置豆包 API」，请检查 `.env` 中 `DOUBAO_API_KEY` 与 `DOUBAO_ENDPOINT_ID` 是否已填写且无多余空格、引号。

---

## 401 / API key format is incorrect 怎么办

豆包返回 **401** 或 **The API key format is incorrect** 时，多半是 **Key 被污染**（复制时带了不可见字符或换行）：

1. **重新复制**：在火山方舟 API Key 页面点击「复制」，不要从邮件或记事本再复制一遍。
2. **.env 里只占一行**：  
   `DOUBAO_API_KEY=粘贴到这里`  
   等号两边不要空格，Key 后面不要引号、不要换行。
3. **手打一遍**：若仍报错，可把 Key 和接入点 ID 删掉，重新手打（或从控制台再次复制后粘贴）。
4. 代码已对 Key 做清洗（去空格、零宽字符），若仍 401，请确认 Key 和接入点 ID 是否在火山方舟当前账号下有效。
