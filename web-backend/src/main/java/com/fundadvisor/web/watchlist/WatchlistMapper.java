package com.fundadvisor.web.watchlist;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Arg;
import org.apache.ibatis.annotations.ConstructorArgs;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface WatchlistMapper {

    @Select("""
            SELECT id, entity_type, entity_code, display_name, created_at
            FROM watchlist_item
            ORDER BY created_at DESC, id DESC
            """)
    @ConstructorArgs({
        @Arg(column = "id", javaType = String.class, id = true),
        @Arg(column = "entity_type", javaType = EntityType.class),
        @Arg(column = "entity_code", javaType = String.class),
        @Arg(column = "display_name", javaType = String.class),
        @Arg(column = "created_at", javaType = Instant.class)
    })
    List<WatchlistItem> findAll();

    @Select("SELECT COUNT(*) FROM watchlist_item")
    int count();

    @Insert("""
            INSERT INTO watchlist_item(id, entity_type, entity_code, display_name, created_at)
            VALUES(#{id}, #{entityType}, #{entityCode}, #{displayName}, #{createdAt})
            """)
    int insert(
            @Param("id") String id,
            @Param("entityType") EntityType entityType,
            @Param("entityCode") String entityCode,
            @Param("displayName") String displayName,
            @Param("createdAt") Instant createdAt);

    @Delete("DELETE FROM watchlist_item WHERE id = #{id}")
    int deleteById(String id);
}
