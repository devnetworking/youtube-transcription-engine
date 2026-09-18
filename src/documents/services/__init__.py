"""One class per capability (section 26): DocumentService owns uploads
and the file library, PDFToMarkdownService/MergeService/SplitService
each own one operation's pipeline, PreviewService owns thumbnails, and
JobService orchestrates submitting/retrying/cancelling jobs against the
job queue. None of them import Flask - routes.py is the only place
that translates between HTTP and these services.
"""
