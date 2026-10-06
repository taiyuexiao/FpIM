-- 评价与反馈（feedback-rating.md，一期）
-- issue_reviews：提问方对已解决问题的评价（评分/标签/评语），一问题一评价
-- product_feedback：员工对平台本身的意见反馈（与业务问题闭环分离）
-- 幂等：可重复执行

CREATE TABLE IF NOT EXISTS public.issue_reviews (
    id          BIGSERIAL PRIMARY KEY,
    issue_id    BIGINT NOT NULL UNIQUE REFERENCES public.issues(id) ON DELETE CASCADE,
    reviewer_id VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    tags        JSONB NOT NULL DEFAULT '[]',
    comment     TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_issue_reviews_reviewer ON public.issue_reviews(reviewer_id);

CREATE TABLE IF NOT EXISTS public.product_feedback (
    id          BIGSERIAL PRIMARY KEY,
    user_id     VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    category    VARCHAR(32) NOT NULL DEFAULT 'other',
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_product_feedback_created ON public.product_feedback(created_at DESC);
