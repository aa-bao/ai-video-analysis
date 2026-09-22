/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  /**
   * 官方脚手架原写作 `DefineComponent<{}, {}, any>`，其中 `{}` 与 `any` 会触发
   * @typescript-eslint/no-empty-object-type / no-explicit-any（较新版本才会报，
   * 故这条门禁此前一直在失败）。`DefineComponent` 的泛型参数本身就有默认值，
   * 省略即等价于脚手架写法，且不再触发这两条规则。
   */
  const component: DefineComponent
  export default component
}
