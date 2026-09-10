package com.fundadvisor.web.interaction;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Arg;
import org.apache.ibatis.annotations.ConstructorArgs;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface PanelCommentMapper {

    @Select("""
            SELECT id, content, client_id, created_at
            FROM panel_comment
            WHERE scope_key = #{scope}
              AND status = 'published'
            ORDER BY created_at DESC, id DESC
            LIMIT #{limit}
            """)
    @ConstructorArgs({
        @Arg(column = "id", javaType = String.class, id = true),
        @Arg(column = "content", javaType = String.class),
        @Arg(column = "client_id", javaType = String.class),
        @Arg(column = "created_at", javaType = Instant.class)
    })
    List<PanelCommentRecord> findRecent(
            @Param("scope") String scope,
            @Param("limit") int limit);

    @Select("""
            SELECT COUNT(*)
            FROM panel_comment
            WHERE scope_key = #{scope}
              AND status = 'published'
            """)
    int countPublished(String scope);

    @Select("""
            SELECT COUNT(*)
            FROM panel_comment
            WHERE client_id = #{clientId}
              AND created_at >= #{since}
            """)
    int countRecentByClient(
            @Param("clientId") String clientId,
            @Param("since") Instant since);

    @Select("""
            SELECT COUNT(*)
            FROM panel_comment
            WHERE scope_key = #{scope}
              AND client_id = #{clientId}
              AND content = #{content}
              AND created_at >= #{since}
            """)
    int countRecentDuplicate(
            @Param("scope") String scope,
            @Param("clientId") String clientId,
            @Param("content") String content,
            @Param("since") Instant since);

    @Insert("""
            INSERT INTO panel_comment(
                id,
                scope_key,
                client_id,
                content,
                status,
                created_at
            )
            VALUES(
                #{id},
                #{scope},
                #{clientId},
                #{content},
                'published',
                #{createdAt}
            )
            """)
    int insert(
            @Param("id") String id,
            @Param("scope") String scope,
            @Param("clientId") String clientId,
            @Param("content") String content,
            @Param("createdAt") Instant createdAt);
}
