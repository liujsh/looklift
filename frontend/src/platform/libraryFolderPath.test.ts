import { describe, expect, it } from "vitest";
import { folderCrumbs } from "./libraryFolderPath";

const roots = [{ id: "r1", path: "C:\\Users\\me\\照片" }];

describe("folderCrumbs", () => {
  it("首页只有首页段", () => {
    expect(folderCrumbs(null, roots)).toEqual([{ label: "首页", path: null }]);
  });

  it("钻进多层时按 root 目录名起、逐段可回退", () => {
    const crumbs = folderCrumbs("C:\\Users\\me\\照片\\2024\\云南", roots);
    expect(crumbs).toEqual([
      { label: "首页", path: null },
      { label: "照片", path: "C:\\Users\\me\\照片" },
      { label: "2024", path: "C:\\Users\\me\\照片\\2024" },
      { label: "云南", path: "C:\\Users\\me\\照片\\2024\\云南" },
    ]);
  });

  it("库外路径只回首页段", () => {
    expect(folderCrumbs("D:\\别处", roots)).toEqual([{ label: "首页", path: null }]);
  });
});
