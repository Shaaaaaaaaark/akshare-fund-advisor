package com.fundadvisor.web.interaction;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Arg;
import org.apache.ibatis.annotations.ConstructorArgs;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

public interface PanelInteractionMapper {

    @Update("""
            UPDATE panel_interaction
            SET option_key = #{optionKey}, updated_at = #{updatedAt}
            WHERE interaction_kind = #{kind}
              AND scope_key = #{scopeKey}
              AND topic_key = #{topicKey}
              AND client_id = #{clientId}
            """)
    int updateChoice(
            @Param("kind") String kind,
            @Param("scopeKey") String scopeKey,
            @Param("topicKey") String topicKey,
            @Param("optionKey") String optionKey,
            @Param("clientId") String clientId,
            @Param("updatedAt") Instant updatedAt);

    @Insert("""
            INSERT INTO panel_interaction(
                id,
                interaction_kind,
                scope_key,
                topic_key,
                option_key,
                client_id,
                created_at,
                updated_at
            )
            VALUES(
                #{id},
                #{kind},
                #{scopeKey},
                #{topicKey},
                #{optionKey},
                #{clientId},
                #{createdAt},
                #{updatedAt}
            )
            """)
    int insert(
            @Param("id") String id,
            @Param("kind") String kind,
            @Param("scopeKey") String scopeKey,
            @Param("topicKey") String topicKey,
            @Param("optionKey") String optionKey,
            @Param("clientId") String clientId,
            @Param("createdAt") Instant createdAt,
            @Param("updatedAt") Instant updatedAt);

    @Select("""
            SELECT option_key
            FROM panel_interaction
            WHERE interaction_kind = #{kind}
              AND scope_key = #{scopeKey}
              AND topic_key = #{topicKey}
              AND client_id = #{clientId}
            """)
    String findSelection(
            @Param("kind") String kind,
            @Param("scopeKey") String scopeKey,
            @Param("topicKey") String topicKey,
            @Param("clientId") String clientId);

    @Select("""
            SELECT option_key, COUNT(*) AS option_count
            FROM panel_interaction
            WHERE interaction_kind = #{kind}
              AND scope_key = #{scopeKey}
              AND topic_key = #{topicKey}
            GROUP BY option_key
            ORDER BY option_key
            """)
    @ConstructorArgs({
        @Arg(column = "option_key", javaType = String.class),
        @Arg(column = "option_count", javaType = Long.class)
    })
    List<InteractionOptionCount> countByOption(
            @Param("kind") String kind,
            @Param("scopeKey") String scopeKey,
            @Param("topicKey") String topicKey);
}
