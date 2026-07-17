# Workflow observability contract

每個 workflow 只能以不變的 `workflow_id` 登錄；顯示名稱可改，workflow JSON 有行為變更時必須遞增 `version`。Dashboard、JobTracker 與 Worker core 不解析 workflow JSON，而是透過 registry 和 adapter 讀取 manifest。

新增 workflow 的完成定義：

1. stable `workflow_id`；
2. semantic `version`；
3. `category` 與 display name；
4. catalog/registry entry；
5. model extraction 或明確 `unknown`；
6. output discovery；
7. node-to-stage mapping；
8. timeout；
9. sensitive fields；
10. successful integration test；
11. failure integration test；
12. Dashboard workflow filter 可見；
13. success rate 與 execution duration 可計算；
14. 每一筆 job 保存 workflow version；
15. 不得修改 Dashboard route/query 或 JobTracker 才能接入。

不確定的 node/model 必須用 `unknown` fallback，不得虛構節點。設定 `WORKFLOW_MANIFEST_POLICY=strict` 時，不完整 manifest 會阻止 Worker 啟動；permissive 僅允許安全 fallback。
