<!-- AI 视频分析：落地页式首屏（Hero + 胶囊搜索条 + 区段）+ 任务执行台。
     首屏版式参考 liyupi/free-video-downloader 的 HeroSection，材质/令牌/动效回到本规约。 -->
<template>
  <div class="page video-page">
    <!-- 首屏 Hero：胶囊徽标 → 大标题（主色尾缀）→ 副标题 → 胶囊搜索条 → 选项行 → 平台胶囊行。
         有选中任务时收窄为 hero--compact，把版面让给下方的执行控制台与结果区。 -->
    <section class="hero" :class="{ 'hero--compact': !!active }" aria-label="视频解析入口">
      <div class="hero__inner">
        <div class="hero__top">
          <span class="hero__badge">
            <span class="hero__badge-dot" aria-hidden="true"></span>
            <!-- 访客配额**只在这一处**出现：剩余条数 + 单条时长上限合成一条
                 （原先徽标说「今日还可解析 N 条」、下面 guest-quota 行又说
                 「单条上限 20 分钟，剩余 5/5 次」，同一件事分两处讲，读起来重复；
                 且配额是**累计**计数、并非每日重置，故去掉「今日」口径）。 -->
            <template v-if="auth.isGuest && quota">免登录体验 · {{ quotaHint }}</template>
            <template v-else>已登录 · 不受访客配额限制</template>
          </span>
        </div>

        <h1 class="hero__title">把一个视频，变成<span class="hero__title-accent">能追问的文稿</span></h1>
        <p class="hero__subtitle">
          支持 bilibili、抖音、微信视频号、小红书图文链接与本地文件；解析过程逐步可见，完成后可下载产物并连续提问。
        </p>

        <!-- 配额耗尽 = 阻断态，独立提示（不是重复文案：徽标只报用量，这里报「怎么办」；
             计数为累计值，故不写「今日」） -->
        <div v-if="auth.isGuest && quota && quotaExhausted" class="guest-quota">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="解析次数已用完"
            :description="`访客最多可解析 ${quota.tasks_max} 条视频，请稍后再试或登录管理员账号。`"
          />
        </div>

        <!-- 主输入：链接走胶囊搜索条（参考项目 HeroSection 的 form 构图） -->
        <form v-if="inputMode === 'url'" class="hero__search glass-surface" @submit.prevent="handleSubmit">
          <label class="sr-only" for="video-url-input">视频链接</label>
          <el-icon class="hero__search-icon" aria-hidden="true"><Link /></el-icon>
          <input
            id="video-url-input"
            ref="urlInputRef"
            v-model="urlInput"
            class="hero__search-input"
            type="text"
            :placeholder="urlPlaceholder"
            :disabled="submitting"
            autocomplete="off"
            @paste="handleUrlPaste"
          />
          <el-button
            class="btn-press hero__search-btn"
            type="primary"
            native-type="submit"
            :loading="submitting"
            :disabled="!urlInput.trim() || quotaExhausted"
          >
            <el-icon v-if="!submitting" class="btn-icon" aria-hidden="true"><VideoPlay /></el-icon>
            开始解析
          </el-button>
        </form>

        <!-- 主输入：本地文件走拖拽上传 -->
        <div v-else class="hero__upload glass-surface">
          <el-upload
            drag
            class="video-uploader"
            :auto-upload="false"
            :limit="1"
            accept="video/*,.mp3,.m4a,.aac,.wav"
            :on-change="handleFileChange"
            :on-remove="() => (localFile = null)"
          >
            <el-icon class="uploader-icon" aria-hidden="true"><UploadFilled /></el-icon>
            <div class="uploader-text">拖拽视频/音频文件到此处，或 <em>点击选择</em></div>
            <template #tip>
              <div class="uploader-tip">支持 mp4 / mov / mkv / webm / mp3 / m4a 等，最大 500MB</div>
            </template>
          </el-upload>
          <el-button
            v-if="localFile"
            class="btn-press hero__upload-btn"
            type="primary"
            :loading="submitting"
            :disabled="quotaExhausted"
            @click="handleFileSubmit"
          >
            <el-icon class="btn-icon" aria-hidden="true"><VideoPlay /></el-icon>
            上传并解析
          </el-button>
        </div>

        <!-- 解析选项：关键帧档位 + 输入方式切换（胶囊 chip，取代旧的 el-tabs 表头） -->
        <div class="hero__options">
          <el-select v-model="frames" class="hero__option" aria-label="关键帧数量">
            <el-option :value="0" label="纯音频（无关键帧）" />
            <el-option :value="8" label="8 帧（精简）" />
            <el-option :value="12" label="12 帧（默认）" />
            <el-option :value="24" label="24 帧（详细）" />
          </el-select>
          <button
            type="button"
            class="chip btn-press"
            :class="{ 'chip--active': inputMode === 'file' }"
            @click="toggleInputMode"
          >
            <el-icon aria-hidden="true"><UploadFilled /></el-icon>
            {{ inputMode === 'file' ? '改用链接' : '本地上传' }}
          </button>
          <span class="hero__options-hint">直接粘贴整段分享文案也会自动提取链接</span>
        </div>

        <!-- 平台渠道：胶囊单选（版式同参考项目的「试试：」示例条，但带真实功能：指定识别渠道） -->
        <div v-if="inputMode === 'url'" class="chip-row hero__channels">
          <span class="chip-row__lead">识别平台：</span>
          <button
            v-for="opt in CHANNEL_OPTIONS"
            :key="opt.value"
            type="button"
            class="chip btn-press"
            :class="{ 'chip--active': channel === opt.value }"
            @click="selectChannel(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>
    </section>

    <!-- 未选中任务时的落地页区段：最近解析 / 能力 / 步骤 / 产物（各自独立组件，见 src/components） -->
    <template v-if="!active">
      <!-- 任务列表在首页的落位：Hero 正下方的内联区段（原为 Hero 右上角按钮弹右侧抽屉） -->
      <section v-if="tasks.length" class="section" aria-labelledby="recent-tasks-heading">
        <SectionHead
          id="recent-tasks-heading"
          title="最近的"
          accent="解析记录"
          :hint="`共 ${tasks.length} 条，点任意一条即可回到该任务继续追问或下载产物。`"
        />
        <TaskList
          :tasks="tasks"
          layout="grid"
          :active-id="null"
          @select="selectTask"
          @remove="removeTask"
        />
      </section>
      <FeatureGrid />
      <HowToSteps />
      <OutputList />
    </template>

    <!-- 任务详情工作区：左侧**常驻任务栏** + 右侧执行/结果工作台。
         「换位置」= 任务列表从右上角按钮弹的右侧抽屉，改为工作区左侧常驻一列，
         可边跑边切任务；抽屉删除（它会盖住内容）。 -->
    <div v-else class="agent-workspace">
      <aside class="task-rail" aria-label="任务列表">
        <div class="task-rail__head">
          <span class="task-rail__title">
            <el-icon aria-hidden="true"><FolderOpened /></el-icon>
            任务列表
          </span>
          <el-button text size="small" class="btn-press" @click="refreshTasks">
            <el-icon class="btn-icon" aria-hidden="true"><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
        <TaskList
          :tasks="tasks"
          layout="rail"
          :active-id="active?.task_id ?? null"
          @select="selectTask"
          @remove="removeTask"
        />
      </aside>

        <section class="agent-layout">
        <!-- 左侧：AI 执行过程 -->
        <aside class="card glass-surface agent-console" aria-label="AI 执行过程">
          <div class="console-head">
            <div>
              <h2 class="card__title">AI 执行过程</h2>
              <p class="console-sub">{{ consoleSubtitle }}</p>
            </div>
            <el-tag :type="taskStatusType(active.status)" size="small" effect="dark" class="console-status">
              {{ taskStatusLabel(active) }}
            </el-tag>
          </div>

          <div v-if="active.status === 'running' || active.status === 'submitted'" class="console-progress">
            <el-progress :percentage="progressPercent" :indeterminate="true" :duration="2" :stroke-width="10" />
          </div>
          <div v-if="active.status === 'failed'" class="console-error">
            <el-alert v-if="cookieError" type="warning" :closable="false" show-icon>
              <template #title>平台 Cookie 已失效</template>
              <p class="cookie-error__hint">当前解析需要平台 Cookie，请提醒管理员更新 <code>rag-service/cookies.txt</code> 后重试。</p>
              <p class="cookie-error__detail">{{ cookieError }}</p>
            </el-alert>
            <el-alert v-else type="error" :closable="false" show-icon>
              <template #title>解析失败</template>
              <p>{{ active.error || '未知错误' }}</p>
            </el-alert>
          </div>

          <div class="phase-list">
            <div v-if="!pipelinePhases.length" class="phase-list-empty">
              正在等待 AI 启动第一步…
            </div>
            <div
              v-for="phase in pipelinePhases"
              :key="phase.id"
              class="phase"
              :class="'phase--' + phase.status"
            >
              <div class="phase__rail">
                <div class="phase__marker">
                  <el-icon v-if="phase.status === 'success'"><CircleCheck /></el-icon>
                  <el-icon v-else-if="phase.status === 'error'"><CircleClose /></el-icon>
                  <el-icon v-else-if="phase.status === 'warning'"><WarningFilled /></el-icon>
                  <el-icon v-else-if="phase.status === 'running'"><Loading class="is-loading" /></el-icon>
                  <el-icon v-else><Minus /></el-icon>
                </div>
              </div>
              <div class="phase__body">
                <div class="phase__head">
                  <span class="phase__title">{{ phase.title }}</span>
                  <span v-if="phase.detail" class="phase__detail">{{ phase.detail }}</span>
                </div>

                <div v-if="phase.id === 'frames' && active.keyframes.length" class="phase-frames">
                  <figure v-for="(kf, idx) in active.keyframes.slice(0, 8)" :key="idx" class="phase-frame">
                    <img :src="frameUrlFor(kf.path)" :alt="'帧 ' + (idx + 1)" loading="lazy" class="phase-frame__img" />
                    <figcaption class="phase-frame__time">{{ formatTimestamp(kf.timestamp_seconds) }}</figcaption>
                  </figure>
                </div>

                <div v-if="phaseLogs(phase.id).length" class="phase-logs">
                  <div v-for="ev in phaseLogs(phase.id)" :key="ev.seq" class="log-line" :class="'log-line--' + ev.level">
                    <span class="log-line__time">{{ formatClock(ev.time) }}</span>
                    <span class="log-line__msg">{{ ev.message }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <!-- 图文模式：中间图文内容 + 右侧图文问答 -->
        <template v-if="isImageTextTask">
          <div class="card glass-surface image-content" aria-label="图文内容">
            <div class="image-content__head">
              <div>
                <h2 class="card__title">图文内容</h2>
                <p v-if="postAuthor || postPublishTime" class="image-content__meta">
                  <span v-if="postAuthor">@{{ postAuthor }}</span>
                  <span v-if="postPublishTime">{{ postPublishTime }}</span>
                </p>
              </div>
              <div class="card__actions">
                <el-button v-if="active.status === 'complete'" text size="small" class="btn-press" @click="openReport">
                  <el-icon class="btn-icon" aria-hidden="true"><Document /></el-icon>
                  HTML 报告
                </el-button>
                <el-button text size="small" class="btn-press" @click="refreshActive">
                  <el-icon class="btn-icon" aria-hidden="true"><Refresh /></el-icon>
                  刷新
                </el-button>
              </div>
            </div>

            <div v-if="postHashtags.length" class="image-content__tags">
              <el-tag v-for="(tag, i) in postHashtags" :key="i" size="small" effect="plain" class="image-tag">{{ tag }}</el-tag>
            </div>

            <div v-if="active.status === 'running' || active.status === 'submitted'" class="image-content__loading">
              <el-icon class="is-loading" aria-hidden="true"><Loading /></el-icon>
              正在抓取图文内容与图片…
            </div>

            <div v-if="active.post_images?.length" class="image-content__gallery">
              <figure v-for="(img, idx) in active.post_images" :key="idx" class="image-content__item">
                <img
                  :src="postImageUrlFor(img.path)"
                  :alt="'图片 ' + (idx + 1)"
                  loading="lazy"
                  class="image-content__img"
                />
                <figcaption class="image-content__caption">
                  <span class="image-content__caption-index">图片 {{ idx + 1 }}</span>
                  <span v-if="imageCaptionFor(idx)" class="image-content__caption-text">{{ imageCaptionFor(idx) }}</span>
                </figcaption>
              </figure>
            </div>

            <div v-if="postText" class="image-content__section">
              <h3 class="section-title">正文</h3>
              <p class="image-content__body">{{ postText }}</p>
            </div>

            <div v-if="summaryText" class="image-content__section">
              <h3 class="section-title">图文摘要</h3>
              <p class="summary-text">{{ summaryText }}</p>
            </div>
          </div>

          <aside class="card glass-surface image-qa" aria-label="图文问答">
            <div class="qa-head">
              <div class="qa-head__text">
                <h2 class="card__title">图文问答</h2>
                <p class="qa-hint">基于文章正文与帖子图片回答，可连续追问。</p>
              </div>
            </div>
            <div class="qa-chat image-qa__chat">
              <div v-if="qaMessages.length === 0 && !qaStreaming" class="qa-empty">
                <el-icon class="qa-empty__icon" aria-hidden="true"><ChatDotRound /></el-icon>
                <p>还没有提问，试试问“这篇图文讲了什么？”</p>
              </div>
              <div v-for="(msg, i) in qaMessages" :key="i" class="qa-msg" :class="msg.role === 'user' ? 'qa-msg--user' : 'qa-msg--assistant'">
                <div v-if="msg.role === 'user'" class="qa-msg__role">你</div>
                <img v-else :src="agentAvatarUrl" class="qa-msg__avatar-img" alt="AI" />
                <div class="qa-msg__bubble">{{ msg.content }}</div>
              </div>
              <div v-if="qaStreaming" class="qa-msg qa-msg--assistant">
                <img :src="agentAvatarUrl" class="qa-msg__avatar-img" alt="AI" />
                <div class="qa-msg__bubble qa-msg__bubble--streaming">
                  <span v-if="!qaStreamingText" class="qa-typing">
                    <span class="qa-typing__dot"></span>
                    <span class="qa-typing__dot"></span>
                    <span class="qa-typing__dot"></span>
                  </span>
                  <template v-else>{{ qaStreamingText }}</template>
                </div>
              </div>
            </div>
            <div class="input-row qa-input">
              <el-input
                v-model="qaQuestion"
                placeholder="就图片或正文继续提问，如：图片里有什么关键信息？"
                clearable
                :disabled="qaLoading"
                @keyup.enter="handleQa"
              />
              <el-button type="primary" class="btn-press" :loading="qaLoading" :disabled="!qaQuestion.trim()" @click="handleQa">
                <el-icon class="btn-icon" aria-hidden="true"><Promotion /></el-icon>
                提问
              </el-button>
            </div>
          </aside>
        </template>

        <!-- 视频模式：右侧结果 + 媒体播放页 -->
        <template v-else>
          <div class="card glass-surface agent-results" aria-label="解析结果">
            <div class="results-head">
              <h2 class="card__title">解析结果</h2>
              <div class="card__actions">
                <el-button v-if="active.status === 'complete'" text size="small" class="btn-press" @click="openReport">
                  <el-icon class="btn-icon" aria-hidden="true"><Document /></el-icon>
                  HTML 报告
                </el-button>
                <el-button text size="small" class="btn-press" @click="refreshActive">
                  <el-icon class="btn-icon" aria-hidden="true"><Refresh /></el-icon>
                  刷新
                </el-button>
              </div>
            </div>

            <div v-if="active.status === 'complete'">
              <div class="detail-meta">
                <span class="meta-item"><b>时长：</b>{{ formatDuration(reportDuration) }}</span>
                <span class="meta-item"><b>转录来源：</b>{{ transcriptSource || '未知' }}</span>
                <span class="meta-item" v-if="costAsr"><b>ASR 成本：</b>¥{{ costAsr }}</span>
              </div>

              <div v-if="summaryText || summaryKeypoints.length || visualNotes.length" class="summary-section">
                <div v-if="summaryText" class="summary-block">
                  <h3 class="section-title">摘要</h3>
                  <p class="summary-text">{{ summaryText }}</p>
                </div>
                <div v-if="summaryKeypoints.length" class="summary-block">
                  <h3 class="section-title">要点</h3>
                  <ul class="summary-list">
                    <li v-for="(kp, i) in summaryKeypoints" :key="i" class="summary-li">{{ kp }}</li>
                  </ul>
                </div>
                <div v-if="visualNotes.length" class="summary-block">
                  <h3 class="section-title">画面洞察</h3>
                  <ul class="summary-list">
                    <li v-for="(note, i) in visualNotes" :key="'v' + i" class="summary-li">{{ note }}</li>
                  </ul>
                </div>
              </div>

              <div v-if="active.keyframes.length" class="frame-section">
                <h3 class="section-title">关键帧</h3>
                <div class="frame-grid">
                  <figure v-for="(kf, idx) in active.keyframes" :key="idx" class="frame-item">
                    <img :src="frameUrlFor(kf.path)" :alt="'关键帧 ' + (idx + 1)" loading="lazy" class="frame-img" />
                    <figcaption class="frame-caption">
                      <span class="frame-caption__time">{{ formatTimestamp(kf.timestamp_seconds) }}</span>
                      <span v-if="frameCaption(kf.timestamp_seconds)" class="frame-caption__text">{{ frameCaption(kf.timestamp_seconds) }}</span>
                      <span v-else class="frame-caption__text frame-caption__text--empty">暂无画面描述</span>
                    </figcaption>
                  </figure>
                </div>
              </div>

              <div v-if="active.transcript" class="transcript-section">
                <h3 class="section-title">转录文本</h3>
                <pre class="transcript-body">{{ active.transcript }}</pre>
              </div>

              <div class="qa-section">
                <div class="qa-head">
                  <div class="qa-head__text">
                    <h3 class="section-title qa-title">视频问答</h3>
                    <p class="qa-hint">基于真实转录与画面内容回答，可连续追问；回答会尽量标注 [MM:SS] 出处。</p>
                  </div>
                  <el-tag size="small" effect="plain" class="qa-model-tag">视频问答 · 流式</el-tag>
                </div>
                <div class="qa-chat">
                  <div v-if="qaMessages.length === 0 && !qaStreaming" class="qa-empty">
                    <el-icon class="qa-empty__icon" aria-hidden="true"><ChatDotRound /></el-icon>
                    <p>还没有提问，试试问“这个视频主要讲了什么？”</p>
                  </div>
                  <div v-for="(msg, i) in qaMessages" :key="i" class="qa-msg" :class="msg.role === 'user' ? 'qa-msg--user' : 'qa-msg--assistant'">
                    <div v-if="msg.role === 'user'" class="qa-msg__role">你</div>
                    <img v-else :src="agentAvatarUrl" class="qa-msg__avatar-img" alt="AI" />
                    <div class="qa-msg__bubble">{{ msg.content }}</div>
                  </div>
                  <div v-if="qaStreaming" class="qa-msg qa-msg--assistant">
                    <img :src="agentAvatarUrl" class="qa-msg__avatar-img" alt="AI" />
                    <div class="qa-msg__bubble qa-msg__bubble--streaming">
                      <span v-if="!qaStreamingText" class="qa-typing">
                        <span class="qa-typing__dot"></span>
                        <span class="qa-typing__dot"></span>
                        <span class="qa-typing__dot"></span>
                      </span>
                      <template v-else>{{ qaStreamingText }}</template>
                    </div>
                  </div>
                </div>
                <div class="input-row qa-input">
                  <el-input
                    v-model="qaQuestion"
                    placeholder="继续深挖细节，如：第二分钟提到的数据是什么？"
                    clearable
                    :disabled="qaLoading"
                    @keyup.enter="handleQa"
                  />
                  <el-button type="primary" class="btn-press" :loading="qaLoading" :disabled="!qaQuestion.trim()" @click="handleQa">
                    <el-icon class="btn-icon" aria-hidden="true"><Promotion /></el-icon>
                    提问
                  </el-button>
                </div>
              </div>
            </div>

            <div v-else-if="active.status === 'running' || active.status === 'submitted'" class="results-running">
              <p class="results-running__text">正在解析中，左侧可实时查看 AI 执行步骤；完成后这里会展示摘要、关键帧、转录与问答。</p>
              <div v-if="active.keyframes.length" class="frame-section">
                <h3 class="section-title">已提取关键帧</h3>
                <div class="frame-grid">
                  <figure v-for="(kf, idx) in active.keyframes" :key="idx" class="frame-item">
                    <img :src="frameUrlFor(kf.path)" :alt="'关键帧 ' + (idx + 1)" loading="lazy" class="frame-img" />
                    <figcaption class="frame-caption">{{ formatTimestamp(kf.timestamp_seconds) }}</figcaption>
                  </figure>
                </div>
              </div>
            </div>

            <div v-else-if="active.status === 'failed'" class="results-failed">
              <el-alert v-if="cookieError" type="warning" :closable="false" show-icon class="cookie-error">
                <template #title>平台 Cookie 已失效</template>
                <p>请提醒管理员更新 <code>rag-service/cookies.txt</code> 后再试。</p>
              </el-alert>
              <p v-else class="results-failed__text">任务失败，左侧执行过程会标出失败位置。</p>
            </div>
          </div>

          <!-- 右侧：媒体播放页（视频 / 音频 / 关键帧预览与下载） -->
          <aside class="card glass-surface media-panel" aria-label="媒体播放">
            <div class="media-head">
              <div>
                <h2 class="card__title">媒体</h2>
                <p class="media-sub">预览与下载视频、音频和关键帧</p>
              </div>
              <el-tag v-if="videoSource" size="small" effect="plain" type="success">可播放</el-tag>
              <el-tag v-else-if="active.status === 'running' || active.status === 'submitted'" size="small" effect="plain" type="info">生成中</el-tag>
            </div>

            <div v-if="videoSource" class="media-block media-block--video">
              <h3 class="media-block__title">视频</h3>
              <video
                :src="videoSource"
                controls
                preload="metadata"
                :poster="posterSource"
                class="media-video"
              ></video>
              <div class="media-actions">
                <a :href="videoDownloadUrl" target="_blank" rel="noopener" class="media-download media-download--primary">
                  <el-icon class="btn-icon" aria-hidden="true"><Download /></el-icon>
                  下载视频
                </a>
              </div>
            </div>
            <div v-else class="media-block media-block--empty">
              <el-icon class="media-empty__icon" aria-hidden="true"><VideoPlay /></el-icon>
              <p>{{ videoPlaceholderText }}</p>
            </div>

            <div v-if="audioSource" class="media-block media-block--audio">
              <h3 class="media-block__title">音频</h3>
              <audio :src="audioSource" controls preload="metadata" class="media-audio"></audio>
              <div class="media-actions">
                <a :href="audioDownloadUrl" target="_blank" rel="noopener" class="media-download">
                  下载音频
                </a>
              </div>
            </div>

            <div v-if="active.keyframes.length" class="media-block media-block--images">
              <h3 class="media-block__title">图片列表</h3>
              <div class="media-images">
                <figure v-for="(kf, idx) in active.keyframes" :key="idx" class="media-image">
                  <img :src="frameUrlFor(kf.path)" :alt="'关键帧 ' + (idx + 1)" loading="lazy" class="media-image__img" />
                  <figcaption class="media-image__meta">
                    <span class="media-image__time">{{ formatTimestamp(kf.timestamp_seconds) }}</span>
                    <a :href="frameUrlFor(kf.path)" :download="'frame-' + (idx + 1) + '.jpg'" class="media-image__download">下载 #{{ idx + 1 }}</a>
                  </figcaption>
                </figure>
              </div>
            </div>
          </aside>
        </template>
      </section>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, CircleCheck, CircleClose, Document, Download, FolderOpened, Link, Loading, Minus, Promotion, Refresh, UploadFilled, VideoPlay, WarningFilled } from '@element-plus/icons-vue'
import FeatureGrid from '../components/FeatureGrid.vue'
import HowToSteps from '../components/HowToSteps.vue'
import OutputList from '../components/OutputList.vue'
import SectionHead from '../components/SectionHead.vue'
import TaskList from '../components/TaskList.vue'
import { formatClock, taskStatusLabel, taskStatusType } from '../utils/task-display'
import { useAuthStore } from '../stores/auth'
import { guestQuotaHint, isQuotaExhausted } from '../api/quota'
import { toAppError } from '../api/errors'
import {
  agentAvatarUrl as getAgentAvatarUrl,
  askQuestionStream,
  deleteTask,
  frameUrl,
  getQaHistory,
  getTask,
  listTasks,
  postImageUrl,
  reportUrl,
  submitFileTask,
  submitUrlTask,
  taskAudioUrl,
  taskEventUrl,
  taskVideoUrl,
  uploadVideoFile,
  type VideoChannel,
  type VideoPipelineEvent,
  type VideoQaMessage,
  type VideoTask,
} from '../api/video'
import { streamSse } from '../api/sse'

const inputMode = ref<'url' | 'file'>('url')
const urlInput = ref('')
const frames = ref(12)
const channel = ref<VideoChannel>('auto')
const CHANNEL_OPTIONS: Array<{ value: VideoChannel; label: string }> = [
  // 首项必须覆盖 ref 默认值 'auto'，否则 el-select 会直接渲染原始值 "auto"
  { value: 'auto', label: '自动识别' },
  { value: 'douyin', label: '抖音' },
  { value: 'bilibili', label: 'B站' },
  { value: 'weixin', label: '微信视频号' },
  { value: 'xiaohongshu', label: '小红书' },
  { value: 'other', label: '其他' },
]
const localFile = ref<File | null>(null)
const submitting = ref(false)

const auth = useAuthStore()
const quota = computed(() => auth.quota)
const quotaExhausted = computed(() => isQuotaExhausted(auth.quota))
const quotaHint = computed(() => guestQuotaHint(auth.quota))

const agentAvatarUrl = getAgentAvatarUrl()
const tasks = ref<VideoTask[]>([])
const active = ref<VideoTask | null>(null)
const qaQuestion = ref('')
const qaLoading = ref(false)
const qaStreaming = ref(false)
const qaStreamingText = ref('')
const qaMessages = ref<VideoQaMessage[]>([])
const pipelineEvents = ref<VideoPipelineEvent[]>([])

let pollTimer: number | undefined
let eventSource: EventSource | null = null

// ── 首屏 Hero 交互 ──
// 能力卡片 / 落地页区段已抽成独立组件（src/components），静态数据随之迁出本文件。

/** 搜索框 DOM 引用：切换识别渠道后把焦点送回输入框，省一次点击 */
const urlInputRef = ref<HTMLInputElement | null>(null)

/** 渠道占位文案：让「识别平台」胶囊的切换在输入框里立刻可见（规约 §8.10 禁止伪功能） */
const CHANNEL_PLACEHOLDER: Record<VideoChannel, string> = {
  auto: '粘贴视频链接，或整段分享文案（自动提取链接）',
  douyin: '粘贴抖音分享文案（含 v.douyin.com 短链）',
  bilibili: '粘贴 bilibili 视频链接或分享文案（含 BV 号）',
  weixin: '粘贴微信视频号分享链接',
  xiaohongshu: '粘贴小红书图文链接或分享文案',
  other: '粘贴视频链接（识别不出平台时选此项）',
}

const urlPlaceholder = computed(() => CHANNEL_PLACEHOLDER[channel.value])

/** 选择渠道：写回 channel + 聚焦输入框。不自动填模板链接，避免用户直接提交到假地址。 */
function selectChannel(value: VideoChannel) {
  channel.value = value
  const el = urlInputRef.value
  if (!el) return
  el.focus()
  const end = el.value.length
  el.setSelectionRange(end, end)
}

/** 链接 / 本地文件两种输入方式互切（取代旧的 el-tabs） */
function toggleInputMode() {
  inputMode.value = inputMode.value === 'file' ? 'url' : 'file'
}

// ── 阶段定义 ──
const PHASE_ORDER = ['prepare', 'acquire', 'audio', 'asr', 'frames', 'visual', 'summary', 'report'] as const
type PhaseId = typeof PHASE_ORDER[number]

interface Phase {
  id: PhaseId
  title: string
  status: 'waiting' | 'running' | 'success' | 'warning' | 'error'
  detail: string
}

function phaseOfStage(stage: string): PhaseId | null {
  const map: Record<string, PhaseId> = {
    starting: 'prepare',
    downloading: 'acquire',
    resolving: 'acquire',
    resolved: 'acquire',
    resolve_failed: 'acquire',
    captions_accepted: 'acquire',
    captions_partial: 'acquire',
    captions_not_found: 'acquire',
    audio_downloaded: 'audio',
    audio_extracted: 'audio',
    transcribing: 'asr',
    asr_planned: 'asr',
    asr_chunk_start: 'asr',
    asr_chunk_done: 'asr',
    asr_chunk_failed: 'asr',
    asr_completed: 'asr',
    asr_partial: 'asr',
    frames_started: 'frames',
    frames_downloaded: 'frames',
    frames_extracted: 'frames',
    frames_failed: 'frames',
    visual_understanding: 'visual',
    summarizing: 'summary',
    summary_completed: 'summary',
    summary_failed: 'summary',
    rendering_report: 'report',
    report_completed: 'report',
    report_failed: 'report',
  }
  return map[stage] ?? null
}

// ── 输入提交 ──

/** 从含有分享文案的文本中提取第一个 http(s) 链接 */
function extractUrlFromText(text: string): string {
  const trimmed = (text || '').trim()
  if (!trimmed) return ''
  const match = trimmed.match(/https?:\/\/[^\s]+/i)
  if (!match) return trimmed
  return match[0].replace(/[),.;!?，。；：！？、）》】"'”’]+$/, '')
}

/** 根据 URL 域名识别平台渠道；识别不到时返回 other */
function detectChannelFromUrl(url: string): VideoChannel | null {
  const value = (url || '').toLowerCase()
  if (!value) return null
  if (/douyin\.com|iesdouyin\.com|v\.douyin\.com/.test(value)) return 'douyin'
  if (/bilibili\.com|b23\.tv/.test(value)) return 'bilibili'
  if (/weixin\.qq\.com\/sph|channels\.weixin\.qq\.com/.test(value)) return 'weixin'
  if (/xiaohongshu\.com|xhslink\.com/.test(value)) return 'xiaohongshu'
  if (/^https?:\/\//.test(value)) return 'other'
  return null
}

function channelLabel(value: VideoChannel): string {
  return CHANNEL_OPTIONS.find((item) => item.value === value)?.label ?? '未知平台'
}

/** 粘贴分享文案时自动提取链接，并识别平台渠道 */
function handleUrlPaste(event: ClipboardEvent) {
  const text = event.clipboardData?.getData('text') || ''
  const url = extractUrlFromText(text)
  if (url && url !== text.trim()) {
    event.preventDefault()
    urlInput.value = url
    applyDetectedChannel(url)
  }
}

function applyDetectedChannel(url: string) {
  const detected = detectChannelFromUrl(url)
  if (!detected) return
  channel.value = detected
  ElMessage.success(`已识别为${channelLabel(detected)}链接`)
}

async function handleSubmit() {
  const raw = urlInput.value.trim()
  if (!raw || submitting.value) return
  if (quotaExhausted.value) {
    ElMessage.warning(auth.quota ? guestQuotaHint(auth.quota) : '解析次数已用完')
    return
  }
  const source = extractUrlFromText(raw)
  if (!source) return
  if (source !== raw) {
    urlInput.value = source
    ElMessage.success('已自动提取链接')
  }
  if (channel.value === 'auto') {
    applyDetectedChannel(source)
  }
  submitting.value = true
  try {
    const task = await submitUrlTask(source, frames.value, channel.value)
    urlInput.value = ''
    channel.value = 'auto'
    await refreshTasks()
    selectTask(task)
  } catch (err) {
    ElMessage.error(toAppError(err).message || '提交失败')
  } finally {
    submitting.value = false
  }
}

watch(urlInput, (value) => {
  const detected = detectChannelFromUrl(extractUrlFromText(value))
  if (detected && detected !== channel.value) {
    channel.value = detected
    ElMessage.success(`已识别为${channelLabel(detected)}链接`)
  }
})

function handleFileChange(file: { raw: File }) {
  localFile.value = file.raw
}

async function handleFileSubmit() {
  if (!localFile.value || submitting.value) return
  if (quotaExhausted.value) {
    ElMessage.warning(auth.quota ? guestQuotaHint(auth.quota) : '解析次数已用完')
    return
  }
  submitting.value = true
  try {
    const uploaded = await uploadVideoFile(localFile.value)
    const task = await submitFileTask(uploaded.path, frames.value)
    localFile.value = null
    await refreshTasks()
    selectTask(task)
  } catch (err) {
    ElMessage.error(toAppError(err).message || '上传失败')
  } finally {
    submitting.value = false
  }
}

// ── 任务管理 ──

async function refreshTasks() {
  try {
    tasks.value = await listTasks()
    if (active.value) {
      const fresh = tasks.value.find((t) => t.task_id === active.value!.task_id)
      if (fresh) active.value = fresh
    }
  } catch {
    /* 列表加载失败静默 */
  }
}

async function selectTask(task: VideoTask) {
  active.value = task
  pipelineEvents.value = [...(task.events || [])]
  qaMessages.value = []
  qaQuestion.value = ''
  qaStreaming.value = false
  qaStreamingText.value = ''
  stopPolling()
  closeEventSource()
  if (task.status === 'complete') {
    await loadQaHistory(task.task_id)
  } else if (task.status === 'running' || task.status === 'submitted') {
    connectEventSource(task.task_id)
    startPolling()
  }
}

async function refreshActive() {
  if (!active.value) return
  try {
    const fresh = await getTask(active.value.task_id)
    active.value = fresh
    const idx = tasks.value.findIndex((t) => t.task_id === fresh.task_id)
    if (idx >= 0) tasks.value[idx] = fresh
    if (fresh.events?.length) {
      pipelineEvents.value = mergeEvents(pipelineEvents.value, fresh.events || [])
    }
    if (fresh.status === 'running' || fresh.status === 'submitted') {
      startPolling()
    } else {
      stopPolling()
      closeEventSource()
      if (fresh.status === 'complete') loadQaHistory(fresh.task_id)
    }
  } catch {
    /* 忽略 */
  }
}

async function removeTask(taskId: string) {
  try {
    await deleteTask(taskId)
    tasks.value = tasks.value.filter((t) => t.task_id !== taskId)
    if (active.value?.task_id === taskId) {
      active.value = null
      pipelineEvents.value = []
      stopPolling()
      closeEventSource()
    }
  } catch {
    ElMessage.error('删除失败')
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(refreshActive, 5000)
}

function stopPolling() {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

// ── SSE 事件流 ──

function connectEventSource(taskId: string) {
  closeEventSource()
  const es = new EventSource(taskEventUrl(taskId))
  eventSource = es

  es.addEventListener('event', (e) => {
    try {
      const ev = JSON.parse((e as MessageEvent).data) as VideoPipelineEvent
      pipelineEvents.value = mergeEvents(pipelineEvents.value, [ev])
      if (ev.stage === 'frames_extracted' && active.value && Array.isArray(ev.data?.keyframes)) {
        active.value = {
          ...active.value,
          keyframes: ev.data.keyframes as VideoTask['keyframes'],
        }
      }
    } catch {
      /* 忽略坏帧 */
    }
  })

  es.addEventListener('done', (e) => {
    try {
      const state = JSON.parse((e as MessageEvent).data) as VideoTask
      active.value = state
      if (state.events?.length) pipelineEvents.value = mergeEvents(pipelineEvents.value, state.events || [])
      if (state.status === 'complete') loadQaHistory(state.task_id)
    } finally {
      stopPolling()
      closeEventSource()
    }
  })

  es.addEventListener('error', () => {
    // 任务已结束或网络断开会触发；由轮询兜底
  })
}

function closeEventSource() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function mergeEvents(current: VideoPipelineEvent[], incoming: VideoPipelineEvent[]): VideoPipelineEvent[] {
  const bySeq = new Map<number, VideoPipelineEvent>()
  for (const ev of [...current, ...incoming]) bySeq.set(ev.seq, ev)
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
}

// ── 问答 ──

async function loadQaHistory(taskId: string) {
  try {
    qaMessages.value = await getQaHistory(taskId)
  } catch {
    qaMessages.value = []
  }
}

async function handleQa() {
  const question = qaQuestion.value.trim()
  if (!question || !active.value || qaLoading.value) return
  qaLoading.value = true
  qaStreaming.value = true
  qaStreamingText.value = ''
  qaMessages.value.push({ role: 'user', content: question })
  qaQuestion.value = ''
  scrollQaToBottom()

  try {
    const resp = await askQuestionStream(active.value.task_id, question)
    if (!resp.ok) {
      const body = await resp.json().catch(() => null) as { error?: { message?: string } } | null
      throw new Error(body?.error?.message || '问答失败')
    }
    let answer = ''
    for await (const ev of streamSse(resp)) {
      if (ev.event === 'chunk') {
        const data = JSON.parse(ev.data) as { content?: string }
        if (data.content) {
          answer += data.content
          qaStreamingText.value = answer
          scrollQaToBottom()
        }
      } else if (ev.event === 'done') {
        const data = JSON.parse(ev.data) as { answer?: string }
        if (data.answer) answer = data.answer
        qaStreaming.value = false
        qaStreamingText.value = ''
        qaMessages.value.push({ role: 'assistant', content: answer })
      } else if (ev.event === 'error') {
        const data = JSON.parse(ev.data) as { message?: string }
        throw new Error(data.message || '问答失败')
      }
    }
    qaStreaming.value = false
    qaStreamingText.value = ''
    scrollQaToBottom()
  } catch (err) {
    qaStreaming.value = false
    qaStreamingText.value = ''
    ElMessage.error((err as { message?: string })?.message || '问答失败')
  } finally {
    qaLoading.value = false
  }
}

function scrollQaToBottom() {
  void nextTick(() => {
    const el = document.querySelector('.qa-chat')
    if (el) el.scrollTop = el.scrollHeight
  })
}

function openReport() {
  if (!active.value) return
  window.open(reportUrl(active.value.task_id), '_blank')
}

// ── 展示辅助 ──

const displayEvents = computed<VideoPipelineEvent[]>(() => {
  if (pipelineEvents.value.length) return pipelineEvents.value
  return derivedEventsFromTask()
})

function derivedEventsFromTask(): VideoPipelineEvent[] {
  const task = active.value
  if (!task) return []
  const evs: VideoPipelineEvent[] = []
  const base = { seq: 0, time: task.created_at || '', title: '', message: '', level: 'success' as const }
  evs.push({ ...base, seq: 1, stage: 'starting', title: '启动解析', message: `开始解析：${task.source}` })
  const ts = task.transcript_source || ''
  if (ts.includes('captions')) {
    evs.push({ ...base, seq: 2, stage: 'captions_accepted', title: '采用平台字幕', message: '字幕覆盖充足，直接使用平台字幕。' })
  } else {
    evs.push({ ...base, seq: 2, stage: 'audio_downloaded', title: '音频处理完成', message: '已获取/提取音频，进入语音转写。' })
  }
  if (task.transcript) {
    evs.push({ ...base, seq: 3, stage: 'asr_completed', title: '语音转写完成', message: `共转写 ${task.transcript.length} 字。` })
  }
  if (task.keyframes.length) {
    evs.push({ ...base, seq: 4, stage: 'frames_extracted', title: '关键帧提取完成', message: `共提取 ${task.keyframes.length} 张关键帧。` })
  }
  if (task.summary?.summary) {
    evs.push({ ...base, seq: 5, stage: 'summary_completed', title: '摘要生成完成', message: `已生成摘要与 ${task.summary.keypoints?.length || 0} 条要点。` })
  }
  if (task.report) {
    evs.push({ ...base, seq: 6, stage: 'report_completed', title: 'HTML 报告已生成', message: '报告渲染完成。' })
  }
  evs.push({ ...base, seq: 7, stage: 'complete', title: '解析完成', message: '全部流程已完成。' })
  return evs
}

const pipelinePhases = computed<Phase[]>(() => {
  const task = active.value
  if (!task) return []
  const statusByPhase = new Map<PhaseId, Phase['status']>()

  for (const id of PHASE_ORDER) {
    const phaseEvents = displayEvents.value.filter((ev) => phaseOfStage(ev.stage) === id)
    if (phaseEvents.length === 0) {
      statusByPhase.set(id, 'waiting')
      continue
    }
    if (phaseEvents.some((ev) => ev.level === 'error')) {
      statusByPhase.set(id, 'error')
    } else if (phaseEvents.some((ev) => ev.level === 'warning')) {
      statusByPhase.set(id, 'warning')
    } else if (phaseEvents.some((ev) => ev.level === 'success')) {
      statusByPhase.set(id, 'success')
    } else if (task.status === 'running' || task.status === 'submitted') {
      const currentStagePhase = task.stage ? phaseOfStage(task.stage) : null
      // 已经发生过的阶段保留展示；正在执行的阶段标 running
      statusByPhase.set(id, currentStagePhase === id ? 'running' : 'success')
    } else {
      statusByPhase.set(id, 'success')
    }
  }

  // 运行中的“当前阶段”即使还没有事件也标为 running
  if (task.status === 'running' || task.status === 'submitted') {
    const current = task.stage ? phaseOfStage(task.stage) : null
    if (current && statusByPhase.get(current) === 'waiting') {
      statusByPhase.set(current, 'running')
    }
  }

  const titles: Record<PhaseId, string> = {
    prepare: '启动任务',
    acquire: '获取视频 / 字幕',
    audio: '音频处理',
    asr: '语音转写（ASR）',
    frames: '关键帧提取',
    visual: '画面理解',
    summary: '摘要生成',
    report: '报告渲染',
  }
  const detailText: Record<PhaseId, string> = {
    prepare: '',
    acquire: '',
    audio: '',
    asr: asrDetail(),
    frames: task.keyframes.length ? `${task.keyframes.length} 帧` : '',
    visual: (task.summary?.visual_notes?.length || task.summary?.keyframe_captions ? Object.keys(task.summary?.keyframe_captions || {}).length : 0) ? '已理解' : '',
    summary: task.summary?.summary ? '已完成' : '',
    report: task.report ? '已完成' : '',
  }

  const allPhases = PHASE_ORDER.map((id) => ({
    id,
    title: titles[id],
    status: statusByPhase.get(id) || 'waiting',
    detail: detailText[id],
  }))

  // 默认不展示全流程：只显示已经发生或正在执行的阶段，
  // 后面的等待阶段等执行到再出现。
  const currentId = task.stage ? phaseOfStage(task.stage) : null
  return allPhases.filter((phase) => {
    if (phase.status !== 'waiting') return true
    if ((task.status === 'submitted' || task.status === 'running') && phase.id === currentId) return true
    if ((task.status === 'submitted' || task.status === 'running') && phase.id === 'prepare') return true
    return false
  })
})

function asrDetail(): string {
  const events = displayEvents.value.filter((ev) => ev.stage === 'asr_completed' || ev.stage === 'asr_partial')
  if (events.length) return events[events.length - 1].message
  const done = displayEvents.value.filter((ev) => ev.stage === 'asr_chunk_done').length
  const total = displayEvents.value.filter((ev) => ev.stage === 'asr_chunk_start').length
  return done && total ? `${done}/${total} 分片完成` : ''
}

function phaseLogs(phaseId: PhaseId): VideoPipelineEvent[] {
  return displayEvents.value.filter((ev) => phaseOfStage(ev.stage) === phaseId)
}

const reportDuration = computed(() => {
  const r = active.value?.report as Record<string, unknown> | null
  return typeof r?.duration_seconds === 'number' ? (r.duration_seconds as number) : 0
})

const transcriptSource = computed(() => {
  const r = active.value?.report as Record<string, unknown> | null
  return typeof r?.transcript_source === 'string' ? (r.transcript_source as string) : ''
})

const costAsr = computed(() => {
  const c = active.value?.cost as Record<string, unknown> | null
  return typeof c?.estimated_asr_cny === 'number' ? String(c.estimated_asr_cny) : ''
})

const summaryText = computed(() => {
  const s = active.value?.summary as { summary?: string } | null
  return typeof s?.summary === 'string' ? (s.summary as string) : ''
})

const summaryKeypoints = computed(() => {
  const s = active.value?.summary as { keypoints?: string[] } | null
  return Array.isArray(s?.keypoints) ? (s.keypoints as string[]) : []
})

const visualNotes = computed(() => {
  const s = active.value?.summary as { visual_notes?: string[] } | null
  return Array.isArray(s?.visual_notes) ? (s.visual_notes as string[]) : []
})

const consoleSubtitle = computed(() => {
  const task = active.value
  if (!task) return ''
  if (task.status === 'complete') return `任务 ${task.task_id} · 已完成`
  if (task.status === 'failed') return `任务 ${task.task_id} · 失败`
  return `任务 ${task.task_id} · ${stageText(task.stage)}`
})

const cookieError = computed<string>(() => {
  const message = active.value?.error || ''
  if (!message) return ''
  const lower = message.toLowerCase()
  if (lower.includes('cookie') || lower.includes('cookies') || (lower.includes('抖音') && lower.includes('登录'))) {
    return message
  }
  return ''
})

function frameCaption(seconds: number): string {
  const captions = active.value?.summary?.keyframe_captions
  if (!captions) return ''
  return captions[formatTimestamp(seconds)] || ''
}

const progressPercent = computed(() => {
  const stage = active.value?.stage
  if (stage === 'complete') return 100
  const map: Record<string, number> = {
    submitted: 5, starting: 10, running: 40, task_started: 15,
    downloading: 18, captions_accepted: 25, audio_downloaded: 30, audio_extracted: 30,
    transcribing: 45, extracting_frames: 50, visual_understanding: 72,
    summarizing: 78, rendering_report: 90,
  }
  return map[stage ?? ''] ?? 45
})

function stageText(stage: string | null): string {
  const map: Record<string, string> = {
    starting: '正在启动解析引擎…',
    running: '解析进行中…',
    downloading: '正在获取视频/字幕…',
    captions_accepted: '已获取平台字幕…',
    audio_downloaded: '音频下载完成…',
    audio_extracted: '音频提取完成，正在转写…',
    transcribing: '正在语音转写（ASR）…',
    extracting_frames: '正在提取关键帧…',
    visual_understanding: '正在理解视频画面…',
    summarizing: '正在生成摘要…',
    rendering_report: '正在渲染报告…',
    frame_extract_failed: '关键帧提取失败（不影响转录）',
    complete: '解析完成',
  }
  return map[stage ?? ''] ?? '解析进行中…'
}

function formatDuration(seconds: number): string {
  if (!seconds) return '未知'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  if (m >= 60) {
    const h = Math.floor(m / 60)
    return `${h} 小时 ${String(m % 60).padStart(2, '0')} 分`
  }
  return `${m} 分 ${String(s).padStart(2, '0')} 秒`
}

function formatTimestamp(seconds: number): string {
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function frameUrlFor(path: string): string {
  const name = path.split(/[\\/]/).pop() ?? ''
  return frameUrl(active.value!.task_id, name)
}

function isPlayableFileTask(task: VideoTask | null): boolean {
  if (!task || task.kind !== 'file') return false
  if (task.video_path) return true
  return /\.(mp4|mkv|webm|mov|m4v|avi|flv|wmv)$/i.test(task.source)
}

const videoSource = computed(() => active.value && (active.value.video_path || isPlayableFileTask(active.value)) ? taskVideoUrl(active.value.task_id) : '')
const audioSource = computed(() => active.value?.audio_path ? taskAudioUrl(active.value.task_id) : '')
const videoDownloadUrl = computed(() => active.value && (active.value.video_path || isPlayableFileTask(active.value)) ? taskVideoUrl(active.value.task_id, true) : '')
const audioDownloadUrl = computed(() => active.value?.audio_path ? taskAudioUrl(active.value.task_id, true) : '')
const posterSource = computed(() => {
  const first = active.value?.keyframes?.[0]
  return first ? frameUrlFor(first.path) : ''
})

const videoPlaceholderText = computed(() => {
  const task = active.value
  if (!task) return '选择任务后显示媒体'
  if (task.kind === 'file') return '本地上传文件已就绪；当前未生成视频预览'
  if (task.status === 'complete') return '该任务没有可播放视频（可能是纯音频模式或下载失败）'
  return '视频将在关键帧阶段下载并保存，稍后即可播放…'
})

const isImageTextTask = computed(() => active.value?.content_type === 'image_text')
const postText = computed(() => active.value?.post_text || '')
const postAuthor = computed(() => active.value?.author || '')
const postHashtags = computed(() => active.value?.hashtags || [])
const postPublishTime = computed(() => active.value?.publish_time || '')
const postImageCaptions = computed(() => active.value?.image_captions || {})

function postImageUrlFor(path: string): string {
  const name = path.split(/[\\/]/).pop() ?? ''
  return postImageUrl(active.value!.task_id, name)
}

function imageCaptionFor(index: number): string {
  return postImageCaptions.value[`图片${index + 1}`] || postImageCaptions.value[String(index + 1)] || ''
}

onMounted(async () => {
  await refreshTasks()
})

onUnmounted(() => {
  stopPolling()
  closeEventSource()
})
</script>

<style scoped>
/* 页面根容器：滚动归 .app-main（AppLayout），这里只负责内边距 */
.page {
  padding: 24px;
}

/* ══════════ 首屏 Hero（版式参考 liyupi/free-video-downloader 的 HeroSection）══════════
   构图：胶囊徽标 → 大标题（主色尾缀）→ 副标题 → 胶囊搜索条 → 选项行 → 平台胶囊行。
   与旧版差异：**不再是整块玻璃卡**，改为开放式居中区段 —— 环境光由 `.app-shell` 的两枚弥散光斑
   提供，玻璃质感集中在搜索条与下方卡片上（规约 §2.1：禁止在浅色玻璃上再叠浅色玻璃）。 */
.hero {
  margin-bottom: 40px;
  padding-top: 16px;
}

.hero__inner {
  max-width: 780px;
  margin: 0 auto;
  text-align: center;
}

/* 顶部只剩状态徽标（任务列表按钮已移走），居中与开放式 Hero 的构图一致 */
.hero__top {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 24px;
}

/* 状态胶囊：玻璃小面 + 绿点（取自 --accent-green，不用 emoji，规约 §2.7） */
.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  background: var(--bg-glass);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  box-shadow: var(--shadow-card);
  color: var(--text-secondary);
  font-size: var(--text-label);
  white-space: nowrap;
}

.hero__badge-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  background: var(--accent-green);
}

.hero__title {
  margin: 0;
  font-size: var(--text-hero);
  font-weight: 800;
  line-height: 1.18;
  letter-spacing: -0.025em;
  color: var(--text-primary);
}

/* 标题主色尾缀：对应参考项目标题里高亮的那半句 */
.hero__title-accent {
  color: var(--accent-blue);
}

/* 窄屏回落：34px 在手机上会把标题挤成三行，退到规约 §3.3 的页面标题档 */
@media (max-width: 640px) {
  .hero__title {
    font-size: var(--text-h1);
  }
}

.hero__subtitle {
  max-width: 620px;
  margin: 14px auto 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

/* ── 访客配额耗尽（阻断态；常态用量提示已并入 Hero 徽标，不再有第二次重复） ── */
.guest-quota {
  max-width: 640px;
  margin: 20px auto 0;
  text-align: left;
}

/* ── 胶囊搜索条：圆角 full + 玻璃面 + 内嵌主按钮 ── */
.hero__search {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 640px;
  margin: 28px auto 0;
  padding: 6px 6px 6px 18px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-card);
}

/* 聚焦环 = 主色描边 + 主色 10% 透明底光晕；不使用 CSS transition（规约 §4 红线） */
.hero__search:focus-within {
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 3px var(--accent-blue-soft), var(--shadow-card);
}

.hero__search-icon {
  flex-shrink: 0;
  font-size: 17px;
  color: var(--text-tertiary);
}

.hero__search-input {
  flex: 1;
  min-width: 0;
  height: 40px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 14px;
  outline: none;
}

.hero__search-input::placeholder {
  color: var(--text-tertiary);
}

.hero__search-input:disabled {
  color: var(--text-tertiary);
  cursor: not-allowed;
}

.hero__search-btn {
  flex-shrink: 0;
  height: 40px;
  padding: 0 22px;
  border-radius: var(--radius-full);
  font-weight: 600;
}

/* 「开始解析」不要旋转 loading —— 旋转的加载图标在胶囊按钮里观感吵闹，
   改为保留原生禁用态（文字变淡）作为唯一反馈。只针对本按钮，
   不动 Element Plus 全局的 .el-icon.is-loading（其它地方仍需要它）。 */
.hero__search-btn :deep(.el-icon.is-loading) {
  animation: none;
}

/* ── 本地上传（取代旧的「本地上传」标签页） ── */
.hero__upload {
  max-width: 640px;
  margin: 28px auto 0;
  padding: 20px;
  border-radius: var(--radius-3xl);
}

.hero__upload-btn {
  width: 100%;
  margin-top: 16px;
}

/* ── 选项行 / 平台渠道行 ── */
.hero__options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 16px;
}

.hero__option {
  width: 176px;
}

.hero__options-hint {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.hero__channels {
  margin-top: 16px;
}

/* 选中任务后收窄 Hero，把版面让给控制台与结果区 */
.hero--compact {
  margin-bottom: 20px;
  padding-top: 0;
}

.hero--compact .hero__title,
.hero--compact .hero__subtitle,
.hero--compact .hero__channels,
.hero--compact .hero__options-hint {
  display: none;
}

.hero--compact .hero__top {
  margin-bottom: 14px;
}

.hero--compact .hero__search,
.hero--compact .hero__upload {
  margin-top: 0;
}

/* ── 表单基础件（问答输入行 / 拖拽区共用） ── */
.btn-icon {
  margin-right: 4px;
}

.input-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.video-uploader {
  width: 100%;
  border-radius: var(--radius-2xl);
}

.uploader-icon {
  font-size: 48px;
  color: var(--text-tertiary);
}

.uploader-text {
  margin-top: 10px;
  font-size: 14px;
  color: var(--text-secondary);
}

.uploader-text em {
  color: var(--accent-blue);
  font-style: normal;
}

.uploader-tip {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ── AI 空状态 ── */
.agent-empty {
  margin-top: 20px;
  padding: 64px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  text-align: center;
}

.agent-empty__icon {
  font-size: 48px;
  color: var(--text-tertiary);
}

.agent-empty__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.agent-empty__text {
  max-width: 480px;
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-secondary);
}

/* ── 工作区：左侧常驻任务栏 + 右侧工作台 ──
   任务栏占掉 208px 后，工作台只剩 ~890px（1600 视口下版心 70% ≈ 1120px）——
   原来的三栏最小宽 1020px 会直接横向溢出，故工作台收成两栏。 */
.agent-workspace {
  display: grid;
  grid-template-columns: 208px minmax(0, 1fr);
  gap: 20px;
  margin-top: 20px;
  align-items: start;
}

.task-rail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-rail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.task-rail__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

/* 窄屏：任务栏收成整宽横排（卡片换行铺满），免得只剩 208px 反而挤压工作台 */
@media (max-width: 1360px) {
  .agent-workspace {
    grid-template-columns: minmax(0, 1fr);
  }

  .task-rail :deep(.task-list--rail) {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .task-rail :deep(.task-card) {
    flex: 1 1 300px;
  }
}

/* ── 工作台（两栏）：第 1 行「执行控制台 | 解析结果」，第 2 行媒体页 / 图文问答**通栏** ──
   通栏而不是挤进右列：媒体页要放播放器 + 下载 + 关键帧网格，图文问答要放气泡，
   两者在 494px 里都太窄；通栏顺带把左列（控制台偏短）的留白补平。 */
.agent-layout {
  display: grid;
  grid-template-columns: minmax(300px, 4fr) minmax(380px, 6fr);
  gap: 20px;
  align-items: start;
}

.agent-layout > *:nth-child(3) {
  grid-column: 1 / -1;
}

@media (max-width: 1100px) {
  .agent-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .agent-layout > *:nth-child(3) {
    grid-column: auto;
  }
}

/* ── 左侧控制台：随内容自然拉伸，不限制高度、不出现内部滚动条 ── */
.agent-console {
  padding: 18px 20px;
}

.console-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.console-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.console-status {
  flex-shrink: 0;
}

.console-progress {
  margin-bottom: 16px;
}

.console-error {
  margin-bottom: 14px;
}

.cookie-error__hint {
  margin: 4px 0 0;
  font-weight: 500;
}

.cookie-error__detail {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
}

.cookie-error code {
  background: var(--bg-subtle);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 12px;
}

.phase-list {
  display: flex;
  flex-direction: column;
}

.phase-list-empty {
  padding: 22px 12px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-tertiary);
  text-align: center;
}

.phase {
  display: flex;
  gap: 12px;
  padding-bottom: 6px;
}

.phase__rail {
  position: relative;
  display: flex;
  justify-content: center;
  width: 28px;
  flex-shrink: 0;
}

.phase:not(:last-child) .phase__rail::after {
  content: '';
  position: absolute;
  top: 28px;
  bottom: 0;
  left: 50%;
  width: 2px;
  transform: translateX(-50%);
  background: var(--border-subtle);
}

.phase__marker {
  position: relative;
  z-index: 1;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--text-tertiary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.phase--success .phase__marker {
  color: var(--accent-green);
  border-color: color-mix(in srgb, var(--accent-green) 45%, transparent);
  background: color-mix(in srgb, var(--accent-green) 10%, transparent);
}

.phase--error .phase__marker {
  color: var(--accent-red);
  border-color: color-mix(in srgb, var(--accent-red) 45%, transparent);
  background: color-mix(in srgb, var(--accent-red) 10%, transparent);
}

.phase--warning .phase__marker {
  color: var(--accent-orange);
  border-color: color-mix(in srgb, var(--accent-orange) 45%, transparent);
  background: color-mix(in srgb, var(--accent-orange) 10%, transparent);
}

.phase--running .phase__marker {
  color: var(--accent-blue);
  border-color: color-mix(in srgb, var(--accent-blue) 45%, transparent);
  background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
}

.phase__body {
  flex: 1;
  min-width: 0;
  padding-bottom: 18px;
}

.phase__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.phase__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.phase__detail {
  font-size: 11.5px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-logs {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.log-line {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.log-line__time {
  flex-shrink: 0;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.log-line--warning {
  color: var(--accent-orange);
}

.log-line--error {
  color: var(--accent-red);
}

.phase-frames {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.phase-frame {
  margin: 0;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
}

.phase-frame__img {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
}

.phase-frame__time {
  padding: 3px 6px;
  font-size: 10px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

/* ── 右侧结果 ── */
.agent-results {
  padding: 18px 20px;
}

.results-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

/* ── 媒体播放页（右侧） ── */
.media-panel {
  padding: 18px 20px;
  position: sticky;
  top: 0;
  max-height: calc(100vh - 140px);
  overflow-y: auto;
}

.media-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.media-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.media-block {
  margin-top: 18px;
}

.media-block + .media-block {
  border-top: 1px solid var(--border-subtle);
  padding-top: 18px;
}

.media-block__title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.media-video {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-2xl);
  background: #000;
  border: 1px solid var(--border-subtle);
  object-fit: contain;
}

.media-audio {
  display: block;
  width: 100%;
}

.media-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.media-download {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  text-decoration: none;
}

.media-download:hover {
  border-color: color-mix(in srgb, var(--accent-blue) 40%, transparent);
  color: var(--accent-blue);
}

.media-download--primary {
  background: var(--text-primary);
  border-color: transparent;
  color: var(--bg-subtle);
}

.media-download--primary:hover {
  background: color-mix(in srgb, var(--text-primary) 88%, var(--accent-blue));
  color: #fff;
  border-color: transparent;
}

.media-block--empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 34px 10px;
  min-height: 180px;
  text-align: center;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-tertiary);
}

.media-block--empty p {
  margin: 0;
  max-width: 240px;
}

.media-empty__icon {
  font-size: 38px;
  color: color-mix(in srgb, var(--accent-blue) 38%, var(--text-tertiary));
}

.media-images {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));
  gap: 10px;
}

.media-image {
  margin: 0;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--bg-subtle);
}

.media-image__img {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
}

.media-image__meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.media-image__download {
  color: var(--accent-blue);
  text-decoration: none;
  font-variant-numeric: normal;
}

.media-image__download:hover {
  text-decoration: underline;
}

.results-running,
.results-failed {
  padding: 40px 12px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.results-failed .cookie-error {
  max-width: 480px;
  margin: 0 auto;
  text-align: left;
}

/* ── 图文模式：中间图文内容 + 右侧图文问答 ── */
.image-content {
  padding: 20px 22px;
}

.image-content__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.image-content__meta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.image-content__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.image-tag {
  border-radius: var(--radius-full);
}

.image-content__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 40px 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.image-content__gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.image-content__item {
  margin: 0;
  border-radius: var(--radius-2xl);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--bg-subtle);
}

.image-content__img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  background: #000;
}

.image-content__caption {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.image-content__caption-index {
  font-variant-numeric: tabular-nums;
}

.image-content__caption-text {
  color: var(--text-secondary);
  line-height: 1.5;
}

.image-content__section {
  margin-top: 18px;
}

.image-content__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.95;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.image-qa {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
}

.image-qa__chat {
  flex: 1;
  margin-top: 12px;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin: 14px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.meta-item b {
  color: var(--text-primary);
  font-weight: 600;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  margin: 22px 0 12px;
}

.summary-section {
  margin-top: 8px;
}

.summary-block {
  margin-bottom: 4px;
}

.summary-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.9;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.summary-list {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-li {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.frame-section {
  margin-top: 4px;
}

.frame-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.frame-item {
  margin: 0;
  border-radius: var(--radius-2xl);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--bg-subtle);
}

.frame-img {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
}

.frame-caption {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 5px 10px;
  font-size: 11px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}

.frame-caption__text {
  color: var(--text-secondary);
  font-variant-numeric: normal;
  letter-spacing: 0;
  line-height: 1.5;
}

.frame-caption__text--empty {
  color: var(--text-tertiary);
  font-style: italic;
  opacity: 0.8;
}

.transcript-section {
  margin-top: 8px;
}

.transcript-body {
  max-height: 340px;
  overflow-y: auto;
  padding: 16px 18px;
  border-radius: var(--radius-2xl);
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.qa-section {
  margin-top: 20px;
  padding-top: 4px;
}

.qa-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.qa-head__text {
  min-width: 0;
}

.qa-title {
  margin: 0 0 6px;
}

.qa-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-tertiary);
}

.qa-model-tag {
  flex-shrink: 0;
  margin-top: 2px;
  border-radius: var(--radius-full);
  letter-spacing: 0.02em;
}

.qa-chat {
  height: min(60vh, 680px);
  min-height: 380px;
  max-height: 680px;
  overflow-y: auto;
  padding: 20px;
  border-radius: var(--radius-3xl);
  background:
    radial-gradient(circle at 90% 0%, color-mix(in srgb, var(--accent-blue) 5%, transparent) 0%, transparent 38%),
    var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-card);
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-behavior: smooth;
}

.qa-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
  padding: 40px 12px;
}

.qa-empty__icon {
  font-size: 34px;
  color: color-mix(in srgb, var(--accent-blue) 45%, var(--text-tertiary));
}

.qa-empty p {
  margin: 0;
}

.qa-msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.qa-msg--user {
  flex-direction: row-reverse;
}

.qa-msg__role {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 700;
  color: var(--bg-elevated);
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-indigo));
  box-shadow: 0 4px 10px -3px color-mix(in srgb, var(--accent-blue) 45%, transparent);
}

.qa-msg__avatar-img {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-full);
  object-fit: cover;
  border: 2px solid color-mix(in srgb, var(--accent-blue) 22%, transparent);
  background: var(--bg-subtle);
  box-shadow: 0 2px 8px -2px rgba(0, 0, 0, 0.08);
}

.qa-msg__bubble {
  max-width: 82%;
  padding: 12px 16px;
  border-radius: 18px 18px 18px 6px;
  font-size: 14px;
  line-height: 1.85;
  color: var(--text-primary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  white-space: pre-wrap;
  word-break: break-word;
}

.qa-msg--user .qa-msg__bubble {
  background: linear-gradient(135deg, var(--accent-blue), color-mix(in srgb, var(--accent-indigo) 75%, var(--accent-blue)));
  border-color: transparent;
  color: var(--bg-elevated);
  border-radius: 18px 18px 6px 18px;
  box-shadow: 0 4px 14px -4px color-mix(in srgb, var(--accent-blue) 50%, transparent);
}

.qa-msg__bubble--streaming {
  background: var(--bg-subtle);
  border: 1px dashed color-mix(in srgb, var(--accent-blue) 45%, transparent);
  color: var(--text-secondary);
}

.qa-typing {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 20px;
}

.qa-typing__dot {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  background: var(--accent-blue);
  opacity: 0.4;
  animation: qaTyping 1.2s ease-in-out infinite;
}

.qa-typing__dot:nth-child(2) {
  animation-delay: 0.15s;
}

.qa-typing__dot:nth-child(3) {
  animation-delay: 0.3s;
}

.qa-input {
  margin-top: 14px;
  padding: 10px;
  border-radius: var(--radius-2xl);
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
}

.qa-input:focus-within {
  border-color: color-mix(in srgb, var(--accent-blue) 45%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-blue) 10%, transparent);
}

@keyframes qaTyping {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
  30% { transform: translateY(-3px); opacity: 1; }
}

.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

</style>
