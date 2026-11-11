---
name: pick_topic
version: 1
variables: interests, region, today, recent_topics, off_limits
---
<topic_pick>
I did not set a topic this week. Please choose one for me, then write the post on it.

My interests: {{interests}}
Region (optional): {{region}}
Today's date: {{today}}
Topics I have already written about recently (do not repeat): {{recent_topics}}
Off limits: {{off_limits}}

How to choose:
- "Trending" here means reported by at least two independent, reputable publishers within the last 10 days of today's date. Use web search. Social-media popularity does not count, because it cannot be measured here and is easily manufactured. If you cannot search the web, say so in <flags> and tell me, and do not guess at current events.
- Shortlist about five candidates close to my interests. For each give a short topic phrase suitable as a weekly focus, the specific angle a post could take, what was reported and when, and its sources.
- Prefer a topic whose angle stays useful after the news cycle ends, where good evidence exists, and where I could plausibly add a view. Prefer a closer fit to my interests over a bigger story.
- Skip breaking tragedies, unverified rumors, partisan politics and celebrity gossip.
- Choose the best one and write the post on it.

In addition to the tags in the reply format, add these two at the very top of your reply:

<topic>The topic you chose, as a short phrase</topic>

<topic_candidates>
1 | topic | angle | why it is trending | url; url
2 | ...
</topic_candidates>
</topic_pick>
