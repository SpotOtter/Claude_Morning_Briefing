ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache nginx python3 tzdata

COPY scripts/ /opt/briefing/scripts/
COPY web/ /opt/briefing/web/
COPY build.sh run.sh /
RUN chmod a+x /build.sh /run.sh

CMD ["/run.sh"]
