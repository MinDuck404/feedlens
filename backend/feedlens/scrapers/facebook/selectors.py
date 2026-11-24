"""CSS selectors substituted into Facebook JavaScript templates."""

SELECTORS = {'__NODES__': 'div[role="feed"] > div, [role="article"], [aria-posinset]',
 '__LINKS__': 'a, [role="link"]',
 '__SELECTOR_3__': 'script[type="application/json"], script[data-sjs]',
 '__SELECTOR_4__': '[data-ad-preview="message"], [data-ad-comet-preview="message"]',
 '__SELECTOR_5__': '[data-feedlens-node]',
 '__SELECTOR_6__': '[role="article"], [aria-posinset]',
 '__SELECTOR_7__': 'div[dir="auto"]',
 '__SELECTOR_8__': 'h2 a, h3 a, h4 a, strong a, h2, h3, h4',
 '__SELECTOR_9__': 'h2, h3, h4, strong',
 '__SELECTOR_10__': 'time, abbr, [data-utime]',
 '__SELECTOR_11__': 'a',
 '__SELECTOR_12__': 'a, span',
 '__SELECTOR_13__': 'h2, h3, h4',
 '__SELECTOR_14__': '*',
 '__SELECTOR_15__': 'blockquote',
 '__SELECTOR_16__': 'div[role="button"]',
 '__SELECTOR_17__': '[data-feedlens-expand]',
 '__SELECTOR_18__': '[role="article"], [aria-posinset], div[role="feed"] > div',
 '__SELECTOR_19__': 'a[href]',
 '__SELECTOR_20__': 'a, [role=link]'}

FB_NODE_SELECTOR = SELECTORS["__NODES__"]
FB_LINK_SELECTOR = SELECTORS["__LINKS__"]
NODE_MARKER = '[data-feedlens-node="{marker}"]'
